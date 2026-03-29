"""BioRxiv / MedRxiv full archive importer.

Uses the official bioRxiv content API to systematically download ALL preprints
in biology-relevant categories from 2019 onward. No scraping — this is the
documented bulk access method.

API: https://api.biorxiv.org/details/{server}/{interval}/{cursor}/json
  Returns 100 papers per call, paginated by cursor.
  For full archive: use date range 2019-01-01 to today.

CLI usage:
    python -m decoded.ingest.bulk_biorxiv --server biorxiv           # All biorxiv
    python -m decoded.ingest.bulk_biorxiv --server medrxiv           # All medrxiv
    python -m decoded.ingest.bulk_biorxiv --server both              # Both
    python -m decoded.ingest.bulk_biorxiv --server biorxiv --from-date 2023-01-01
    python -m decoded.ingest.bulk_biorxiv --limit 50000             # Cap at 50k

    # Second pass — fetch full JATS XML for papers that only have abstracts:
    python -m decoded.ingest.bulk_biorxiv --phase fulltext           # Upgrade fetched→parsed
    python -m decoded.ingest.bulk_biorxiv --phase fulltext --concurrency 4
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import uuid
from datetime import date, timedelta
from pathlib import Path

import httpx
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=True)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("decoded.ingest.bulk_biorxiv")

BIORXIV_API = "https://api.biorxiv.org/details"
MEDRXIV_API = "https://api.medrxiv.org/details"
DATA_DIR = _ROOT / "data" / "biorxiv_bulk"

# Biology-relevant categories for filtering
# Set to None to import everything (all categories)
RELEVANT_CATEGORIES = {
    "biochemistry", "bioinformatics", "biology", "biophysics",
    "cancer-biology", "cell-biology", "developmental-biology",
    "evolutionary-biology", "genetics", "genomics", "immunology",
    "microbiology", "molecular-biology", "neuroscience", "pharmacology",
    "physiology", "plant-biology", "scientific-communication",
    "systems-biology", "synthetic-biology",
    # medRxiv categories
    "aging", "cardiovascular", "endocrinology", "gastroenterology",
    "geriatric", "infectious-diseases", "metabolism", "neurology",
    "oncology", "ophthalmology", "pediatrics", "pharmacology",
    "psychiatry", "respiratory", "rheumatology",
}


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    return conn


def get_existing_dois(conn, source: str) -> set[str]:
    cur = conn.cursor()
    cur.execute("SELECT external_id FROM raw_papers WHERE source=%s", (source,))
    return {str(r[0]) for r in cur.fetchall()}


def insert_papers_batch(conn, run_id: str, records: list[dict]) -> tuple[int, int]:
    """Bulk insert papers. Returns (new_count, skipped_count)."""
    if not records:
        return 0, 0

    from datetime import datetime
    cur = conn.cursor()
    new_count = 0

    for rec in records:
        pub_date = rec.get("pub_date")
        pub_date_obj = None
        pub_year = None
        if pub_date and len(str(pub_date)) >= 4:
            try:
                if len(pub_date) == 4:
                    pub_date = f"{pub_date}-01-01"
                pub_date_obj = datetime.strptime(pub_date[:10], "%Y-%m-%d").date()
                pub_year = pub_date_obj.year
            except ValueError:
                pass

        paper_id = str(uuid.uuid4())
        status = "fetched" if rec.get("abstract") else "queued"

        try:
            cur.execute(
                """
                INSERT INTO raw_papers (
                    id, source, external_id, title, abstract, authors, journal,
                    published_date, pub_year, doi, pmc_id, keywords, mesh_terms,
                    status, ingest_run_id, raw_metadata, sections,
                    reference_count, references_list, created_at, updated_at
                ) VALUES (
                    %s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,NOW(),NOW()
                )
                ON CONFLICT (source, external_id) DO NOTHING
                RETURNING id
                """,
                (
                    paper_id,
                    rec["source"],
                    rec["external_id"],
                    (rec.get("title") or "")[:2000],
                    rec.get("abstract"),
                    json.dumps(rec.get("authors") or []),
                    rec.get("journal"),
                    pub_date_obj,
                    pub_year,
                    rec.get("doi"),
                    None,  # pmc_id
                    json.dumps(rec.get("keywords") or []),
                    json.dumps([]),
                    status,
                    run_id,
                    json.dumps(rec.get("raw_metadata") or {}),
                    json.dumps({}),
                    0,
                    json.dumps([]),
                ),
            )
            if cur.fetchone():
                new_count += 1
        except Exception as exc:
            logger.debug("Insert failed for %s: %s", rec.get("external_id"), exc)

    conn.commit()
    return new_count, len(records) - new_count


# ---------------------------------------------------------------------------
# BioRxiv / MedRxiv API paginator
# ---------------------------------------------------------------------------

def _normalize(item: dict, server: str) -> dict | None:
    """Normalize a biorxiv/medrxiv API result to our schema."""
    doi = (item.get("doi") or "").strip()
    if not doi:
        return None

    abstract = (item.get("abstract") or "").strip()
    if len(abstract) < 30:
        return None

    pub_date = item.get("date") or item.get("date_timestamp", "")
    pub_year = None
    if pub_date and len(str(pub_date)) >= 4:
        try:
            pub_year = int(str(pub_date)[:4])
        except ValueError:
            pass

    authors_raw = item.get("authors", "")
    authors = [a.strip() for a in authors_raw.split(";") if a.strip()]

    category = (item.get("category") or "").strip().lower()

    return {
        "source": server,
        "external_id": doi,
        "title": (item.get("title") or "").strip(),
        "abstract": abstract,
        "authors": authors,
        "journal": "medRxiv" if server == "medrxiv" else "bioRxiv",
        "pub_date": pub_date,
        "pub_year": pub_year,
        "doi": doi,
        "keywords": [category] if category else [],
        "raw_metadata": {
            "category": category,
            "version": item.get("version"),
            "jatsxml": item.get("jatsxml"),
            "server": server,
        },
    }


async def fetch_date_range(
    server: str,
    date_from: str,
    date_to: str,
    existing_dois: set[str],
    cursor: int = 0,
    limit: int = 0,
    filter_categories: bool = True,
) -> tuple[list[dict], int, int]:
    """Fetch all papers in a date range. Returns (records, total_fetched, new_count)."""
    base_url = MEDRXIV_API if server == "medrxiv" else BIORXIV_API
    all_records: list[dict] = []
    total_in_range = 0
    page = cursor
    consecutive_all_existing = 0

    async with httpx.AsyncClient(timeout=60, follow_redirects=True) as client:
        while True:
            url = f"{base_url}/{server}/{date_from}/{date_to}/{page}/json"
            try:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("API request failed (cursor=%d): %s", page, exc)
                await asyncio.sleep(5)
                break

            messages = data.get("messages", [{}])
            if messages:
                total_in_range = messages[0].get("total", total_in_range)

            collection = data.get("collection", [])
            if not collection:
                break

            batch_new = 0
            for item in collection:
                rec = _normalize(item, server)
                if rec is None:
                    continue
                if filter_categories and RELEVANT_CATEGORIES:
                    cat = (rec.get("keywords") or [""])[0]
                    if cat and cat not in RELEVANT_CATEGORIES:
                        continue
                if rec["external_id"] not in existing_dois:
                    all_records.append(rec)
                    existing_dois.add(rec["external_id"])
                    batch_new += 1

            if batch_new == 0:
                consecutive_all_existing += 1
                if consecutive_all_existing >= 3:
                    logger.debug("3 consecutive all-existing pages, stopping early")
                    break
            else:
                consecutive_all_existing = 0

            page += len(collection)

            if page % 5000 == 0:
                logger.info(
                    "  %s %s→%s: cursor=%d total=%d new_so_far=%d",
                    server, date_from, date_to, page, total_in_range, len(all_records),
                )

            if len(collection) < 100:
                break

            if limit and len(all_records) >= limit:
                break

            await asyncio.sleep(0.5)  # polite delay

    return all_records, total_in_range, len(all_records)


# ---------------------------------------------------------------------------
# Main import
# ---------------------------------------------------------------------------

async def run_bulk_import(
    server: str = "biorxiv",
    date_from: str = "2019-01-01",
    date_to: str | None = None,
    limit: int = 0,
    batch_size: int = 500,
):
    """Import all preprints from a server between date_from and date_to."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    if date_to is None:
        date_to = date.today().isoformat()

    servers = ["biorxiv", "medrxiv"] if server == "both" else [server]
    conn = get_db_conn()

    for srv in servers:
        logger.info(
            "Starting bulk import: %s %s → %s",
            srv.upper(), date_from, date_to,
        )

        existing_dois = get_existing_dois(conn, srv)
        logger.info("  Already in DB: %d %s papers", len(existing_dois), srv)

        # Create ingest run
        cur = conn.cursor()
        run_id = str(uuid.uuid4())
        cur.execute(
            "INSERT INTO ingest_runs (id, domain, ring, source, query, max_results) VALUES (%s,%s,%s,%s,%s,%s)",
            (run_id, "longevity", 0, srv, f"bulk_{srv}_{date_from}_{date_to}", limit or 999999),
        )
        conn.commit()

        # Split into monthly chunks for better progress visibility and resilience
        from_dt = date.fromisoformat(date_from)
        to_dt = date.fromisoformat(date_to)
        total_imported = 0
        total_found = 0

        # Process in 3-month chunks
        chunk_start = from_dt
        while chunk_start < to_dt:
            chunk_end = min(
                date(chunk_start.year + (chunk_start.month + 2) // 12,
                     (chunk_start.month + 2) % 12 or 12, 1) - timedelta(days=1),
                to_dt,
            )

            logger.info(
                "  Chunk: %s → %s", chunk_start.isoformat(), chunk_end.isoformat()
            )

            records, chunk_total, chunk_new = await fetch_date_range(
                server=srv,
                date_from=chunk_start.isoformat(),
                date_to=chunk_end.isoformat(),
                existing_dois=existing_dois,
                limit=max(0, limit - total_imported) if limit else 0,
            )

            total_found += chunk_total

            # Insert in batches
            for i in range(0, len(records), batch_size):
                batch = records[i:i + batch_size]
                new, skipped = insert_papers_batch(conn, run_id, batch)
                total_imported += new

            logger.info(
                "  Chunk %s→%s: %d new / %d found (running total: %d)",
                chunk_start.isoformat(), chunk_end.isoformat(),
                len(records), chunk_total, total_imported,
            )

            if limit and total_imported >= limit:
                break

            chunk_start = chunk_end + timedelta(days=1)
            await asyncio.sleep(1)

        # Finish ingest run
        cur.execute(
            "UPDATE ingest_runs SET papers_found=%s, papers_new=%s, status='completed', completed_at=NOW() WHERE id=%s",
            (total_found, total_imported, run_id),
        )
        conn.commit()
        logger.info(
            "%s bulk import complete: %d new papers imported",
            srv.upper(), total_imported,
        )

    conn.close()


# ---------------------------------------------------------------------------
# Full-text second pass
# ---------------------------------------------------------------------------

async def _get_jatsxml_url(doi: str, server: str, client: httpx.AsyncClient) -> str | None:
    """Ask the biorxiv/medrxiv API for the JATS XML URL for a given DOI."""
    base = MEDRXIV_API if server == "medrxiv" else BIORXIV_API
    url = f"{base}/{server}/{doi}/na/json"
    try:
        resp = await client.get(url, timeout=20)
        resp.raise_for_status()
        collection = resp.json().get("collection", [])
        if collection:
            return collection[0].get("jatsxml")
    except Exception:
        pass
    return None


async def _fetch_and_parse_fulltext(
    paper_id: str,
    doi: str,
    server: str,
    semaphore: asyncio.Semaphore,
    client: httpx.AsyncClient,
) -> dict | None:
    """Fetch JATS XML for one paper. Returns parsed dict or None."""
    async with semaphore:
        # Step 1: get jatsxml URL from API
        jatsxml_url = await _get_jatsxml_url(doi, server, client)
        if not jatsxml_url:
            return None

        await asyncio.sleep(0.3)  # polite delay

        # Step 2: download the XML
        try:
            resp = await client.get(jatsxml_url, timeout=60, follow_redirects=True)
            resp.raise_for_status()
            xml_bytes = resp.content
        except Exception as exc:
            logger.debug("XML download failed for %s: %s", doi, exc)
            return None

        # Step 3: parse with existing JATS parser
        from decoded.ingest.parse import parse_article
        parsed = parse_article("jats", xml_bytes)
        if not parsed:
            return None

        return parsed


async def run_fulltext_phase(
    concurrency: int = 4,
    limit: int = 0,
    sources: list[str] | None = None,
):
    """Second pass: fetch full JATS XML for biorxiv/medrxiv papers that only have abstracts.

    Finds all papers with status='fetched' (abstract only, no full text),
    downloads JATS XML from bioRxiv content server, parses, and updates to status='parsed'.
    """
    if sources is None:
        sources = ["biorxiv", "medrxiv"]

    conn = get_db_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    placeholders = ", ".join(["%s"] * len(sources))
    query = f"""
        SELECT id, doi, source, title
        FROM raw_papers
        WHERE source IN ({placeholders})
          AND status = 'fetched'
          AND doi IS NOT NULL
          AND (full_text IS NULL OR full_text = '')
        ORDER BY pub_year DESC NULLS LAST
        {"LIMIT %s" if limit else ""}
    """
    params = list(sources) + ([limit] if limit else [])
    cur.execute(query, params)
    papers = cur.fetchall()

    logger.info(
        "Full-text second pass: %d biorxiv/medrxiv papers to upgrade",
        len(papers),
    )

    if not papers:
        logger.info("Nothing to do — all papers already have full text or no DOI")
        conn.close()
        return

    semaphore = asyncio.Semaphore(concurrency)
    stats = {"upgraded": 0, "no_xml": 0, "errors": 0}

    async with httpx.AsyncClient(
        timeout=60,
        follow_redirects=True,
        headers={"User-Agent": "Decoded-Research-Pipeline/1.0 (research; mailto:research@thedecodedhuman.com)"},
    ) as client:

        async def process_one(paper: dict):
            doi = paper["doi"]
            server = paper["source"]
            paper_id = str(paper["id"])

            parsed = await _fetch_and_parse_fulltext(paper_id, doi, server, semaphore, client)

            if parsed is None:
                stats["no_xml"] += 1
                return

            # Build UPDATE params — only set fields that were successfully parsed
            updates = ["status='parsed'", "updated_at=NOW()"]
            vals: list = []

            if parsed.get("full_text"):
                updates.append("full_text=%s")
                vals.append(parsed["full_text"])
            if parsed.get("sections"):
                updates.append("sections=%s")
                vals.append(json.dumps(parsed["sections"]))
            if parsed.get("abstract") and not paper.get("abstract"):
                updates.append("abstract=%s")
                vals.append(parsed["abstract"])
            if parsed.get("authors"):
                updates.append("authors=%s")
                vals.append(json.dumps(parsed["authors"]))
            if parsed.get("reference_count"):
                updates.append("reference_count=%s")
                vals.append(parsed["reference_count"])
            if parsed.get("references"):
                updates.append("references_list=%s")
                vals.append(json.dumps(parsed["references"][:500]))

            vals.append(paper_id)
            update_cur = conn.cursor()
            update_cur.execute(
                f"UPDATE raw_papers SET {', '.join(updates)} WHERE id=%s",
                vals,
            )
            conn.commit()
            stats["upgraded"] += 1

            if stats["upgraded"] % 100 == 0:
                logger.info(
                    "Full-text progress: %d upgraded, %d no_xml, %d errors",
                    stats["upgraded"], stats["no_xml"], stats["errors"],
                )

        tasks = [process_one(p) for p in papers]
        await asyncio.gather(*tasks, return_exceptions=True)

    conn.close()
    logger.info(
        "Full-text phase complete: %d upgraded to parsed, %d no XML available, %d errors",
        stats["upgraded"], stats["no_xml"], stats["errors"],
    )
    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="BioRxiv/MedRxiv full archive bulk importer"
    )
    parser.add_argument("--phase", choices=["import", "fulltext"], default="import",
                        help="import=bulk date-range import, fulltext=upgrade abstracts to full text")
    parser.add_argument("--server", choices=["biorxiv", "medrxiv", "both"], default="biorxiv")
    parser.add_argument("--from-date", default="2019-01-01", help="Start date (YYYY-MM-DD)")
    parser.add_argument("--to-date", default=None, help="End date (default: today)")
    parser.add_argument("--limit", type=int, default=0, help="Max papers to import/upgrade (0=all)")
    parser.add_argument("--batch-size", type=int, default=500, help="DB insert batch size")
    parser.add_argument("--concurrency", type=int, default=4, help="Concurrent fetches for fulltext phase")
    parser.add_argument(
        "--all-categories", action="store_true",
        help="Import all categories (default: biology-relevant only)"
    )
    args = parser.parse_args()

    if args.phase == "fulltext":
        sources = (
            ["biorxiv", "medrxiv"] if args.server == "both"
            else [args.server]
        )
        asyncio.run(run_fulltext_phase(
            concurrency=args.concurrency,
            limit=args.limit,
            sources=sources,
        ))
    else:
        asyncio.run(run_bulk_import(
            server=args.server,
            date_from=args.from_date,
            date_to=args.to_date,
            limit=args.limit,
            batch_size=args.batch_size,
        ))


if __name__ == "__main__":
    main()
