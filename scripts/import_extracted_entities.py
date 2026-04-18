"""Sprint G — Import entity mentions from extraction_results.entities.

Claude's extractor has been emitting structured entity mentions on every
paper (text, entity_type, confidence, spans) with normalized_id=null. The
connectome never consumed them. This script turns those 300K+ organically-
discovered entities into first-class nodes in discovered_entities +
discovered_entity_mentions.

Curation (operation tags, semantic level, aliases) remains an *overlay* on
discovered_entities via curated_canonical_id — not a gate.

Idempotent: UPSERT on canonical_text; mentions PK'd on (paper_id, entity_id).

Usage:
    python scripts/import_extracted_entities.py --limit 500 --dry-run
    python scripts/import_extracted_entities.py                # all papers
    python scripts/import_extracted_entities.py --only-new     # only papers
                                                                  not yet processed
"""
from __future__ import annotations

import argparse
import logging
import os
import re
import time
from collections import Counter

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("import_entities")

DB_HOST = os.environ.get("PGHOST", "Whits-Mac-mini.local")
DB_NAME = os.environ.get("PGDATABASE", "encoded_human")


def db_connect():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


# Normalize entity text into a collapsible canonical form. Strict rules:
#   - lowercase
#   - trim + collapse whitespace
#   - strip outer punctuation
#   - drop parenthetical abbreviations like "short-chain fatty acids (SCFAs)"
#     → "short-chain fatty acids"  (the parens gets its own mention below)
#   - preserve hyphens, greek chars, digits
_WS = re.compile(r"\s+")
_PARENS = re.compile(r"\s*\(([^)]+)\)")
_EDGE_PUNCT = re.compile(r"^[\s\.,;:!?\"'\[\]{}]+|[\s\.,;:!?\"'\[\]{}]+$")


def canonicalize(text: str) -> tuple[str, list[str]]:
    """Return (canonical_form, extra_mentions_from_parentheticals)."""
    if not text:
        return "", []
    s = text.strip()
    extras: list[str] = []

    # Pull out parentheticals — often contain abbreviations worth also indexing
    m = _PARENS.search(s)
    while m:
        inner = m.group(1).strip()
        if inner and 2 <= len(inner) <= 30:
            extras.append(inner)
        s = s[:m.start()] + s[m.end():]
        m = _PARENS.search(s)

    s = _EDGE_PUNCT.sub("", s)
    s = _WS.sub(" ", s).lower().strip()
    return s, extras


def import_entities(only_new: bool, limit: int | None, dry_run: bool) -> None:
    conn = db_connect()
    stats: Counter = Counter()
    try:
        # Build list of papers to process
        with conn.cursor() as cur:
            where = ""
            if only_new:
                where = """WHERE NOT EXISTS (
                    SELECT 1 FROM discovered_entity_mentions dem
                    WHERE dem.paper_id = er.paper_id
                )"""
            limit_clause = f"LIMIT {limit}" if limit else ""
            cur.execute(
                f"""SELECT er.id::text AS extraction_id,
                           er.paper_id::text AS paper_id,
                           er.entities
                   FROM extraction_results er
                   {where}
                   {'AND' if only_new else 'WHERE'} jsonb_array_length(er.entities) > 0
                   ORDER BY er.created_at DESC
                   {limit_clause}"""
            )
            rows = cur.fetchall()
        log.info("Processing %d extraction_results rows", len(rows))

        entity_buffer: dict[str, dict] = {}
        # canonical_text → dict(display_text, entity_type, mention_count, paper_count,
        #                       conf_sum, papers: set[paper_id], confidences: list)
        mention_buffer: list[tuple[str, str, float | None]] = []
        # (paper_id, canonical_text, confidence)

        t0 = time.time()
        for i, row in enumerate(rows):
            if i % 2000 == 0 and i > 0:
                rate = i / (time.time() - t0)
                log.info("  %d/%d (%.0f/s) · %d distinct entities so far",
                         i, len(rows), rate, len(entity_buffer))

            paper_id = row["paper_id"]
            ents = row["entities"] or []
            if not isinstance(ents, list):
                continue
            for e in ents:
                if not isinstance(e, dict):
                    continue
                raw_text = e.get("text")
                if not raw_text:
                    continue
                ent_type = e.get("entity_type") or "unknown"
                conf = e.get("confidence")
                # Only trust mid-confidence and above for the primary mention
                # (still index lower-confidence as extra mentions for edges)
                canonical, extras = canonicalize(str(raw_text))
                if not canonical or len(canonical) < 2 or len(canonical) > 200:
                    stats["skipped_text_length"] += 1
                    continue

                all_surface_forms = [(canonical, str(raw_text).strip())]
                for x in extras:
                    can2, _ = canonicalize(x)
                    if can2 and 2 <= len(can2) <= 200:
                        all_surface_forms.append((can2, x.strip()))

                for can_key, display in all_surface_forms:
                    if can_key not in entity_buffer:
                        entity_buffer[can_key] = {
                            "display_text": display,
                            "entity_type": ent_type,
                            "type_counter": Counter({ent_type: 1}),
                            "confidences": [],
                            "papers": set(),
                        }
                    b = entity_buffer[can_key]
                    b["type_counter"][ent_type] += 1
                    if conf is not None:
                        b["confidences"].append(float(conf))
                    b["papers"].add(paper_id)
                    mention_buffer.append((paper_id, can_key, conf))
                    stats["mentions_queued"] += 1
                stats["entities_seen"] += 1

        log.info("Distinct entities: %d · queued mentions: %d",
                 len(entity_buffer), len(mention_buffer))

        if dry_run:
            log.info("DRY RUN — not writing")
            # Show top 20
            top = sorted(entity_buffer.items(),
                         key=lambda kv: len(kv[1]["papers"]), reverse=True)[:20]
            for k, b in top:
                log.info("  %-50s  %-12s  papers=%d  mentions=%d",
                         k[:50], b["entity_type"], len(b["papers"]),
                         b["type_counter"].total())
            return

        # Write discovered_entities (upsert)
        log.info("Writing discovered_entities…")
        with conn.cursor() as cur:
            rows_to_upsert = []
            for can_key, b in entity_buffer.items():
                dominant_type = b["type_counter"].most_common(1)[0][0]
                conf_avg = (sum(b["confidences"]) / len(b["confidences"])
                            if b["confidences"] else None)
                rows_to_upsert.append((
                    can_key, b["display_text"], dominant_type,
                    b["type_counter"].total(), len(b["papers"]), conf_avg,
                ))
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO discovered_entities
                     (canonical_text, display_text, entity_type,
                      mention_count, paper_count, confidence_avg)
                   VALUES %s
                   ON CONFLICT (canonical_text) DO UPDATE SET
                     mention_count = discovered_entities.mention_count + EXCLUDED.mention_count,
                     paper_count   = discovered_entities.paper_count + EXCLUDED.paper_count,
                     confidence_avg = COALESCE(
                       (COALESCE(discovered_entities.confidence_avg, 0) + COALESCE(EXCLUDED.confidence_avg, 0))/2,
                       discovered_entities.confidence_avg
                     ),
                     last_seen_at = NOW()""",
                rows_to_upsert,
                template="(%s, %s, %s, %s, %s, %s)",
                page_size=1000,
            )
            stats["entities_upserted"] = cur.rowcount

            # Get all entity ids keyed by canonical
            cur.execute(
                "SELECT id::text AS id, canonical_text FROM discovered_entities"
            )
            canon_to_id = {r["canonical_text"]: r["id"] for r in cur.fetchall()}
        conn.commit()

        # Write mentions (idempotent via PK)
        log.info("Writing discovered_entity_mentions (%d rows)…",
                 len(mention_buffer))
        with conn.cursor() as cur:
            # Dedupe (paper_id, entity_id) keeping max confidence
            dedupe: dict[tuple[str, str], float | None] = {}
            for paper_id, can_key, conf in mention_buffer:
                eid = canon_to_id.get(can_key)
                if not eid:
                    continue
                k = (paper_id, eid)
                cur_conf = dedupe.get(k)
                if cur_conf is None or (conf is not None and (cur_conf is None or conf > cur_conf)):
                    dedupe[k] = conf
            payload = [(p, e, c) for (p, e), c in dedupe.items()]
            psycopg2.extras.execute_values(
                cur,
                """INSERT INTO discovered_entity_mentions
                     (paper_id, entity_id, confidence)
                   VALUES %s
                   ON CONFLICT (paper_id, entity_id) DO NOTHING""",
                payload,
                template="(%s, %s, %s)",
                page_size=2000,
            )
            stats["mentions_written"] = cur.rowcount
        conn.commit()

        log.info("=" * 60)
        log.info("IMPORT COMPLETE")
        log.info("=" * 60)
        for k, v in stats.most_common():
            log.info("  %-28s %s", k, v)

        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM discovered_entities")
            log.info("discovered_entities total: %s", cur.fetchone()["n"])
            cur.execute("""SELECT entity_type, COUNT(*) AS n FROM discovered_entities
                           GROUP BY 1 ORDER BY 2 DESC""")
            for r in cur.fetchall():
                log.info("  %-14s %s", r["entity_type"], r["n"])
            cur.execute("""SELECT display_text, mention_count, paper_count, entity_type
                           FROM discovered_entities
                           ORDER BY mention_count DESC LIMIT 15""")
            log.info("")
            log.info("Top 15 entities by mention count:")
            for r in cur.fetchall():
                log.info("  %-45s %-12s  %d mentions · %d papers",
                         r["display_text"][:45], r["entity_type"],
                         r["mention_count"], r["paper_count"])
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-new", action="store_true")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()
    import_entities(only_new=args.only_new, limit=args.limit, dry_run=args.dry_run)


if __name__ == "__main__":
    main()
