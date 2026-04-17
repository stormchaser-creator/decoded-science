"""IngestWorker: orchestrates discover → fetch → parse → store.

CLI usage:
    python -m decoded.ingest.worker --ring ring_0 --limit 100
    python -m decoded.ingest.worker --ring ring_0 --limit 100 --query "cerebral aneurysm neuroinflammation"
    python -m decoded.ingest.worker --ring ring_1 --domain longevity --limit 500
"""

from __future__ import annotations

import argparse
import asyncio
import gzip
import json
import logging
import os
import sys
import uuid
from datetime import datetime, date
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

# Load .env from project root
_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=False)

from decoded.ingest.discover import PMCDiscoverer
from decoded.ingest.fetch import PMCFetcher
from decoded.ingest.parse import JATSParser, BioCParser, parse_article
from decoded.ingest.europepmc import EuropePMCDiscoverer
from decoded.ingest.arxiv import ArxivDiscoverer

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("decoded.ingest.worker")

# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def get_db_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    return conn


def upsert_paper(conn, record: dict[str, Any], run_id: str) -> tuple[str, bool]:
    """Insert or update a paper. Returns (paper_id, is_new)."""
    cur = conn.cursor()

    source = record.get("source", "pubmed")
    external_id = record.get("external_id") or record.get("pmid", "")
    if not external_id:
        return "", False

    # Check existence
    cur.execute(
        "SELECT id, status FROM raw_papers WHERE source = %s AND external_id = %s",
        (source, external_id),
    )
    existing = cur.fetchone()

    if existing:
        paper_id, current_status = existing
        # Don't downgrade status
        if current_status not in ("queued", "error"):
            return str(paper_id), False
        cur.execute(
            "UPDATE raw_papers SET updated_at = NOW() WHERE id = %s",
            (str(paper_id),),
        )
        conn.commit()
        return str(paper_id), False

    # Build insert dict
    pub_date = record.get("pub_date")
    if isinstance(pub_date, str) and len(pub_date) >= 4:
        try:
            # Normalize to date
            if len(pub_date) == 4:
                pub_date = f"{pub_date}-01-01"
            pub_date_obj = datetime.strptime(pub_date[:10], "%Y-%m-%d").date()
        except ValueError:
            pub_date_obj = None
    else:
        pub_date_obj = None

    pub_year = record.get("pub_year")
    if pub_year is None and pub_date_obj:
        pub_year = pub_date_obj.year

    paper_id = str(uuid.uuid4())

    # SAVEPOINT wrapper — a single paper's unique-constraint collision
    # (e.g. source+title duplicate) should not abort the whole ingest run.
    import psycopg2.errors as _pgerr
    cur.execute("SAVEPOINT sp_upsert_paper")
    try:
        cur.execute(
            """
            INSERT INTO raw_papers (
                id, source, external_id, title, abstract, authors, journal,
                published_date, pub_year, doi, pmc_id, mesh_terms, keywords,
                status, ingest_run_id, raw_metadata, sections, reference_count,
                references_list, created_at, updated_at
            ) VALUES (
                %s, %s, %s, %s, %s, %s, %s,
                %s, %s, %s, %s, %s, %s,
                'queued', %s, %s, %s, %s,
                %s, NOW(), NOW()
            )
            ON CONFLICT (source, external_id) DO NOTHING
            RETURNING id
            """,
            (
                paper_id,
                source,
                external_id,
                record.get("title", "")[:2000],
                record.get("abstract"),
                json.dumps(record.get("authors", [])),
                record.get("journal"),
                pub_date_obj,
                pub_year,
                record.get("doi"),
                record.get("pmc_id"),
                json.dumps(record.get("mesh_terms", [])),
                json.dumps(record.get("keywords", [])),
                run_id,
                json.dumps(record.get("raw_metadata", {})),
                json.dumps({}),
                None,
                json.dumps([]),
            ),
        )
        row = cur.fetchone()
        cur.execute("RELEASE SAVEPOINT sp_upsert_paper")
        conn.commit()
        if row:
            return str(row[0]), True
        return paper_id, False
    except _pgerr.UniqueViolation as e:
        cur.execute("ROLLBACK TO SAVEPOINT sp_upsert_paper")
        conn.commit()
        logger.warning(
            "upsert_paper UniqueViolation (skipping): source=%s external_id=%s title=%r %s",
            source, external_id, (record.get("title") or "")[:80],
            str(e).strip().split("\n")[0][:200],
        )
        return "", False
    except Exception:
        cur.execute("ROLLBACK TO SAVEPOINT sp_upsert_paper")
        conn.commit()
        raise


def update_paper_fetched(conn, paper_id: str, pmc_id: str | None):
    """Mark paper as fetching."""
    cur = conn.cursor()
    cur.execute(
        "UPDATE raw_papers SET status='fetching', pmc_id=%s, updated_at=NOW() WHERE id=%s",
        (pmc_id, paper_id),
    )
    conn.commit()


def update_paper_parsed(conn, paper_id: str, parsed: dict[str, Any]):
    """Store parsed data and mark as parsed."""
    cur = conn.cursor()

    pub_date = parsed.get("pub_date")
    pub_date_obj = None
    if isinstance(pub_date, str) and len(pub_date) >= 4:
        try:
            if len(pub_date) == 4:
                pub_date = f"{pub_date}-01-01"
            pub_date_obj = datetime.strptime(pub_date[:10], "%Y-%m-%d").date()
        except ValueError:
            pass

    pub_year = parsed.get("pub_year")
    if pub_year is None and pub_date_obj:
        pub_year = pub_date_obj.year

    sections = parsed.get("sections") or {}
    refs = parsed.get("references") or []
    ref_count = parsed.get("reference_count") or len(refs)

    updates: list[str] = ["status='parsed'", "updated_at=NOW()"]
    params: list[Any] = []

    if parsed.get("title"):
        updates.append("title=%s")
        params.append(parsed["title"][:2000])
    if parsed.get("abstract"):
        updates.append("abstract=%s")
        params.append(parsed["abstract"])
    if parsed.get("full_text"):
        updates.append("full_text=%s")
        params.append(parsed["full_text"])
    if parsed.get("journal"):
        updates.append("journal=%s")
        params.append(parsed["journal"])
    if pub_date_obj:
        updates.append("published_date=%s")
        params.append(pub_date_obj)
    if pub_year:
        updates.append("pub_year=%s")
        params.append(pub_year)
    if parsed.get("doi"):
        updates.append("doi=%s")
        params.append(parsed["doi"])
    if parsed.get("authors"):
        updates.append("authors=%s")
        params.append(json.dumps(parsed["authors"]))

    updates.append("sections=%s")
    params.append(json.dumps(sections))
    updates.append("reference_count=%s")
    params.append(ref_count)
    updates.append("references_list=%s")
    params.append(json.dumps(refs[:500]))  # cap at 500 refs

    params.append(paper_id)
    cur.execute(
        f"UPDATE raw_papers SET {', '.join(updates)} WHERE id=%s",
        params,
    )
    conn.commit()


def update_paper_error(conn, paper_id: str, error: str):
    cur = conn.cursor()
    cur.execute(
        "UPDATE raw_papers SET status='error', raw_metadata = raw_metadata || %s, updated_at=NOW() WHERE id=%s",
        (json.dumps({"error": error[:500]}), paper_id),
    )
    conn.commit()


def create_ingest_run(conn, domain: str, ring: int, source: str, query: str, max_results: int) -> str:
    cur = conn.cursor()
    run_id = str(uuid.uuid4())
    cur.execute(
        """
        INSERT INTO ingest_runs (id, domain, ring, source, query, max_results)
        VALUES (%s, %s, %s, %s, %s, %s)
        """,
        (run_id, domain, ring, source, query, max_results),
    )
    conn.commit()
    return run_id


def finish_ingest_run(conn, run_id: str, found: int, new_: int, skipped: int, status: str = "completed", error: str | None = None):
    cur = conn.cursor()
    cur.execute(
        """
        UPDATE ingest_runs
        SET papers_found=%s, papers_new=%s, papers_skipped=%s,
            status=%s, error=%s, completed_at=NOW()
        WHERE id=%s
        """,
        (found, new_, skipped, status, error, run_id),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# IngestWorker
# ---------------------------------------------------------------------------


class IngestWorker:
    """Orchestrate discover → fetch → parse → store for one query."""

    def __init__(
        self,
        ring: int,
        query: str,
        limit: int = 200,
        domain: str = "longevity",
        source: str = "pubmed",
        date_from: str | None = None,
        date_to: str | None = None,
        raw_xml_dir: Path | None = None,
        dry_run: bool = False,
    ):
        self.ring = ring
        self.query = query
        self.limit = limit
        self.domain = domain
        self.source = source
        self.date_from = date_from
        self.date_to = date_to
        self.dry_run = dry_run

        api_key = os.environ.get("NCBI_API_KEY")
        if source in ("biorxiv", "medrxiv"):
            self.discoverer = EuropePMCDiscoverer()
            self.fetcher = None
        elif source == "arxiv":
            self.discoverer = ArxivDiscoverer()
            self.fetcher = None
        else:
            self.discoverer = PMCDiscoverer(api_key=api_key)
            self.fetcher = PMCFetcher(raw_xml_dir=raw_xml_dir)

    async def run(self) -> dict[str, int]:
        """Run the full ingest pipeline. Returns stats dict."""
        if self.source in ("biorxiv", "medrxiv", "arxiv"):
            return await self._run_preprint_ingest()
        return await self._run_pubmed_ingest()

    async def _run_preprint_ingest(self) -> dict[str, int]:
        """Ingest biorxiv/medrxiv/arxiv preprints (abstract-only, no full-text fetch)."""
        conn = get_db_conn()
        run_id = create_ingest_run(
            conn, self.domain, self.ring, self.source, self.query, self.limit
        )
        logger.info(
            "Starting preprint ingest: source=%s ring=%d query='%s' limit=%d",
            self.source, self.ring, self.query, self.limit,
        )

        stats = {"found": 0, "new": 0, "skipped": 0, "fetched": 0, "parsed": 0, "errors": 0}

        try:
            if self.source == "arxiv":
                records = await self.discoverer.discover(
                    query=self.query,
                    max_results=self.limit,
                )
            else:
                records = await self.discoverer.discover(
                    query=self.query,
                    max_results=self.limit,
                    server=self.source,
                )
            stats["found"] = len(records)
            logger.info("Discovered %d %s preprints", len(records), self.source)

            if self.dry_run:
                for r in records[:5]:
                    logger.info("  [dry-run] %s | %s", r.get("external_id"), r.get("title", "")[:80])
                return stats

            for rec in records:
                paper_id, is_new = upsert_paper(conn, rec, run_id)
                if not paper_id:
                    stats["skipped"] += 1
                    continue
                if not is_new:
                    stats["skipped"] += 1
                    continue
                stats["new"] += 1

                # Mark as fetched immediately — abstract is available for extraction
                if rec.get("abstract"):
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE raw_papers SET status='fetched', updated_at=NOW() WHERE id=%s AND status='queued'",
                        (paper_id,),
                    )
                    conn.commit()
                    stats["fetched"] += 1

            finish_ingest_run(
                conn, run_id,
                found=stats["found"],
                new_=stats["new"],
                skipped=stats["skipped"],
            )
            logger.info(
                "Preprint ingest complete: found=%d new=%d fetched=%d skipped=%d",
                stats["found"], stats["new"], stats["fetched"], stats["skipped"],
            )

        except Exception as exc:
            logger.error("Preprint ingest failed: %s", exc, exc_info=True)
            finish_ingest_run(conn, run_id, 0, 0, 0, status="failed", error=str(exc))
            raise
        finally:
            conn.close()

        return stats

    async def _run_pubmed_ingest(self) -> dict[str, int]:
        """Original PubMed ingest: discover → fetch PMC full text → parse."""
        conn = get_db_conn()
        run_id = create_ingest_run(
            conn, self.domain, self.ring, self.source, self.query, self.limit
        )
        logger.info(
            "Starting ingest: ring=%d query='%s' limit=%d run_id=%s",
            self.ring, self.query, self.limit, run_id,
        )

        stats = {"found": 0, "new": 0, "skipped": 0, "fetched": 0, "parsed": 0, "errors": 0}

        try:
            # --- DISCOVER ---
            logger.info("Discovering PMIDs via PubMed esearch...")
            records = await self.discoverer.discover(
                query=self.query,
                max_results=self.limit,
                date_from=self.date_from,
                date_to=self.date_to,
            )
            stats["found"] = len(records)
            logger.info("Discovered %d papers", len(records))

            if self.dry_run:
                for r in records[:5]:
                    logger.info("  [dry-run] %s | %s", r.get("pmid"), r.get("title", "")[:80])
                return stats

            # --- STORE metadata + UPSERT ---
            paper_ids: list[tuple[str, str | None]] = []  # (paper_id, pmc_id)
            for rec in records:
                rec["source"] = "pubmed"
                rec["external_id"] = rec.get("pmid", "")
                paper_id, is_new = upsert_paper(conn, rec, run_id)
                if not paper_id:
                    stats["skipped"] += 1
                    continue
                if is_new:
                    stats["new"] += 1
                else:
                    stats["skipped"] += 1
                    continue  # Don't re-fetch existing papers
                pmc_id = rec.get("pmc_id")
                paper_ids.append((paper_id, pmc_id, rec))

            logger.info(
                "Upserted %d new papers, %d skipped (already exist)",
                stats["new"], stats["skipped"],
            )

            # Mark abstract-only papers as 'fetched' so extraction can use them
            no_pmc_papers = [(pid, rec) for pid, pmcid, rec in paper_ids if not pmcid]
            for pid, rec in no_pmc_papers:
                if rec.get("abstract"):
                    cur = conn.cursor()
                    cur.execute(
                        "UPDATE raw_papers SET status='fetched', updated_at=NOW() WHERE id=%s AND status='queued'",
                        (pid,),
                    )
                    conn.commit()

            # --- FETCH + PARSE (only papers with PMC IDs) ---
            pmc_papers = [(pid, pmcid, rec) for pid, pmcid, rec in paper_ids if pmcid]
            no_pmc = len(paper_ids) - len(pmc_papers)
            logger.info(
                "%d papers have PMCIDs (full text available), %d abstract-only",
                len(pmc_papers), no_pmc,
            )

            # Process with concurrency
            sem = asyncio.Semaphore(5)
            tasks = [
                self._fetch_parse_store(conn, paper_id, pmcid, rec, sem, stats)
                for paper_id, pmcid, rec in pmc_papers
            ]
            await asyncio.gather(*tasks, return_exceptions=True)

            finish_ingest_run(
                conn, run_id,
                found=stats["found"],
                new_=stats["new"],
                skipped=stats["skipped"],
            )
            logger.info(
                "Ingest complete: found=%d new=%d fetched=%d parsed=%d errors=%d",
                stats["found"], stats["new"], stats["fetched"],
                stats["parsed"], stats["errors"],
            )

        except Exception as exc:
            logger.error("Ingest run failed: %s", exc, exc_info=True)
            finish_ingest_run(conn, run_id, 0, 0, 0, status="failed", error=str(exc))
            raise
        finally:
            conn.close()

        return stats

    async def _fetch_parse_store(
        self,
        conn,
        paper_id: str,
        pmcid: str,
        pubmed_rec: dict,
        sem: asyncio.Semaphore,
        stats: dict,
    ):
        async with sem:
            try:
                update_paper_fetched(conn, paper_id, pmcid)

                result = await self.fetcher.fetch(pmcid)
                if result is None:
                    update_paper_error(conn, paper_id, "fetch_failed: no content retrieved")
                    stats["errors"] += 1
                    return

                fmt, gz_content = result
                stats["fetched"] += 1

                # Decompress and parse
                raw_content = gzip.decompress(gz_content)
                parsed = parse_article(fmt, raw_content)

                if not parsed:
                    update_paper_error(conn, paper_id, "parse_failed: empty result")
                    stats["errors"] += 1
                    return

                # Merge PubMed metadata that BioC might lack
                if not parsed.get("authors") and pubmed_rec.get("authors"):
                    parsed["authors"] = pubmed_rec["authors"]
                if not parsed.get("abstract") and pubmed_rec.get("abstract"):
                    parsed["abstract"] = pubmed_rec["abstract"]
                if not parsed.get("title") and pubmed_rec.get("title"):
                    parsed["title"] = pubmed_rec["title"]
                if not parsed.get("journal") and pubmed_rec.get("journal"):
                    parsed["journal"] = pubmed_rec["journal"]
                if not parsed.get("pub_date") and pubmed_rec.get("pub_date"):
                    parsed["pub_date"] = pubmed_rec["pub_date"]

                update_paper_parsed(conn, paper_id, parsed)
                stats["parsed"] += 1
                logger.debug("Parsed %s (%s)", pmcid, parsed.get("title", "")[:60])

            except Exception as exc:
                logger.warning("Error processing %s/%s: %s", paper_id, pmcid, exc)
                try:
                    update_paper_error(conn, paper_id, str(exc)[:500])
                except Exception:
                    pass
                stats["errors"] += 1


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _parse_ring(ring_str: str) -> int:
    """Accept 'ring_0', 'ring0', '0', 0."""
    ring_str = str(ring_str).lower().replace("ring", "").replace("_", "").strip()
    val = int(ring_str)
    if val not in (0, 1, 2):
        raise argparse.ArgumentTypeError(f"Ring must be 0, 1, or 2 (got {val})")
    return val


async def _async_main(args):
    if args.query:
        # Ad-hoc query override
        queries = [(args.ring, args.query)]
    else:
        # Load from domain config
        from decoded.config.seed_domain import get_domain
        domain_cfg = get_domain(args.domain)
        ring_queries = domain_cfg.all_queries()
        # Filter to requested ring
        queries = [(ring, q) for ring, q in ring_queries if ring == args.ring]

    total_limit = args.limit
    per_query_limit = total_limit // max(len(queries), 1)
    per_query_limit = max(per_query_limit, 10)

    all_stats: list[dict] = []
    remaining = total_limit

    for ring, q in queries:
        if remaining <= 0:
            break
        query_str = q.query if hasattr(q, "query") else q
        date_from = q.date_from if hasattr(q, "date_from") else None
        date_to = q.date_to if hasattr(q, "date_to") else None
        this_limit = min(per_query_limit, remaining)

        source = q.source if hasattr(q, "source") else "pubmed"
        worker = IngestWorker(
            ring=ring,
            query=query_str,
            limit=this_limit,
            domain=args.domain,
            source=source,
            date_from=date_from,
            date_to=date_to,
            raw_xml_dir=Path(args.raw_xml_dir) if args.raw_xml_dir else None,
            dry_run=args.dry_run,
        )
        stats = await worker.run()
        all_stats.append(stats)
        remaining -= stats.get("found", 0)

        if args.first_only:
            break

    # Summary
    totals = {k: sum(s.get(k, 0) for s in all_stats) for k in ("found", "new", "fetched", "parsed", "errors", "skipped")}
    logger.info("=== FINAL SUMMARY ===")
    for k, v in totals.items():
        logger.info("  %s: %d", k, v)
    return totals


def main():
    parser = argparse.ArgumentParser(
        description="Decoded ingest worker — discover, fetch, and parse PMC papers"
    )
    parser.add_argument("--ring", type=_parse_ring, default=0,
                        help="Ring level: ring_0, ring_1, ring_2 (or 0/1/2)")
    parser.add_argument("--limit", type=int, default=200,
                        help="Max number of papers to ingest (default: 200)")
    parser.add_argument("--domain", default="longevity",
                        help="Seed domain (default: longevity)")
    parser.add_argument("--query", default=None,
                        help="Override seed query with a custom query string")
    parser.add_argument("--date-from", default=None,
                        help="Filter papers from this date (YYYY-MM-DD)")
    parser.add_argument("--date-to", default=None,
                        help="Filter papers up to this date (YYYY-MM-DD)")
    parser.add_argument("--raw-xml-dir", default=None,
                        help="Directory to store raw XML (default: data/raw_xml/)")
    parser.add_argument("--first-only", action="store_true",
                        help="Only run the first seed query (for testing)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Discover only, do not store to DB")
    args = parser.parse_args()

    asyncio.run(_async_main(args))


if __name__ == "__main__":
    main()
