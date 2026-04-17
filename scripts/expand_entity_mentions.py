"""Sprint G — Substring entity-mention expansion.

The extractor produces prose for triple objects:
   CCM1 → induces → "Oxidative stress and inflammatory response"
   CCM1 → correlates_with → "Perturbed progesterone signaling, BBB dysfunction, vascular malformation"

Normalization matches the WHOLE STRING to canonical names/aliases. The whole
string "Oxidative stress and inflammatory response" is never a canonical —
so it never resolves, the edge dead-ends at prose, and graph traversal
terminates.

Fix: scan every triple's subject and object for canonical entity names and
aliases as whole-word substrings. Materialize every match into a new table
`triple_entity_mentions(triple_id, entity_id, role, match_text)`.

Edge synthesis then JOINs paper_claim_triples × triple_entity_mentions twice
(once for subject side, once for object side), producing one edge per
(subject_entity × object_entity) cross-product for each triple. CCM1 → induces
→ "Oxidative stress and inflammatory response" becomes TWO edges:
    CCM1 → induces → Oxidative stress
    CCM1 → induces → Inflammation

Idempotent via PRIMARY KEY (triple_id, entity_id, role, match_text).

Usage:
    python scripts/expand_entity_mentions.py --dry-run
    python scripts/expand_entity_mentions.py
    python scripts/expand_entity_mentions.py --only-new    # triples with no existing mentions
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
log = logging.getLogger("expand_mentions")

DB_HOST = os.environ.get("PGHOST", "Whits-Mac-mini.local")
DB_NAME = os.environ.get("PGDATABASE", "encoded_human")


def db_connect():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS triple_entity_mentions (
    triple_id   UUID NOT NULL REFERENCES paper_claim_triples(id) ON DELETE CASCADE,
    entity_id   UUID NOT NULL REFERENCES canonical_entities(id) ON DELETE CASCADE,
    role        TEXT NOT NULL CHECK (role IN ('subject', 'object')),
    match_text  TEXT NOT NULL,
    match_source TEXT NOT NULL DEFAULT 'substring'
                 CHECK (match_source IN ('canonical_exact','alias_exact',
                                         'canonical_substring','alias_substring')),
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    PRIMARY KEY (triple_id, entity_id, role, match_text)
);

CREATE INDEX IF NOT EXISTS idx_tem_entity ON triple_entity_mentions (entity_id);
CREATE INDEX IF NOT EXISTS idx_tem_role ON triple_entity_mentions (role);
CREATE INDEX IF NOT EXISTS idx_tem_triple ON triple_entity_mentions (triple_id);
"""


def ensure_schema(cur):
    cur.execute(SCHEMA_SQL)


def load_entity_patterns(cur) -> tuple[re.Pattern, dict[str, dict]]:
    """Build one compiled regex alternation for ALL canonical entity strings
    (canonical_name + aliases), sorted longest-first so multi-word phrases
    match greedily. Returns (pattern, match_lookup_dict).

    match_lookup_dict maps normalized_matched_string → {entity_id, source}.
    """
    cur.execute(
        "SELECT id::text AS id, canonical_name, aliases FROM canonical_entities"
    )
    rows = cur.fetchall()

    entries: list[tuple[str, str, str]] = []  # (matched_text, entity_id, source)
    for r in rows:
        name = r["canonical_name"]
        if name:
            entries.append((name, r["id"], "canonical"))
        for a in (r["aliases"] or []):
            if a and len(a.strip()) >= 2:
                entries.append((a, r["id"], "alias"))

    # Deduplicate by lowercased string (prefer canonical over alias)
    seen: dict[str, tuple[str, str]] = {}
    for text, ent_id, source in entries:
        key = text.lower().strip()
        if not key or len(key) < 2:
            continue
        # Skip strings shorter than 2 chars (regex would blow up)
        # Prefer canonical entries on collision
        if key in seen:
            prev_src = seen[key][1]
            if prev_src == "canonical":
                continue
        seen[key] = (ent_id, source)

    # Sort by length desc so multi-word match wins before shorter substring
    sorted_keys = sorted(seen.keys(), key=lambda s: (-len(s), s))

    # Build alternation pattern. Escape each alternative.
    # Use whole-word boundaries via lookbehind/lookahead so "IL-6" matches
    # in "IL-6 expression" but not "mIL-6x". For terms containing non-word
    # chars (hyphens, greek, digits), \b doesn't always work — use
    # (?<![A-Za-z0-9])...(?![A-Za-z0-9]) which is more robust for biomed.
    escaped = [re.escape(k) for k in sorted_keys]
    # Word-ish boundaries
    alt = "|".join(escaped)
    pattern_str = r"(?<![A-Za-z0-9])(" + alt + r")(?![A-Za-z0-9])"
    pattern = re.compile(pattern_str, flags=re.IGNORECASE)

    # Lookup: lowercased match text → (entity_id, source)
    lookup = {k: {"entity_id": v[0], "source": v[1]} for k, v in seen.items()}

    log.info("Built pattern with %d distinct entity strings (len %d chars)",
             len(seen), len(pattern_str))
    return pattern, lookup


def scan_triples(dry_run: bool, only_new: bool, limit: int | None) -> None:
    conn = db_connect()
    stats: Counter = Counter()

    try:
        with conn.cursor() as cur:
            ensure_schema(cur)
            conn.commit()

            pattern, lookup = load_entity_patterns(cur)

            # Fetch triples to scan
            where_clause = ""
            if only_new:
                where_clause = """
                  WHERE NOT EXISTS (
                    SELECT 1 FROM triple_entity_mentions tem
                    WHERE tem.triple_id = pct.id
                  )
                """
            limit_clause = f"LIMIT {limit}" if limit else ""
            log.info("Fetching triples%s…", " (only new)" if only_new else "")
            cur.execute(
                f"""SELECT pct.id::text AS id, pct.subject, pct.object
                   FROM paper_claim_triples pct
                   {where_clause}
                   {limit_clause}"""
            )
            rows = cur.fetchall()
            stats["triples_scanned"] = len(rows)
            log.info("Scanning %d triples…", len(rows))

        # Build insert batch
        batch: list[tuple[str, str, str, str, str]] = []
        t0 = time.time()
        for i, row in enumerate(rows):
            if i % 10000 == 0 and i > 0:
                elapsed = time.time() - t0
                rate = i / elapsed
                log.info("  scanned %d/%d (%.0f/sec) — mentions so far: %d",
                         i, len(rows), rate, stats["mentions_found"])

            subj = row["subject"] or ""
            obj = row["object"] or ""

            # Subject matches
            for m in pattern.finditer(subj):
                mt = m.group(1)
                info = lookup.get(mt.lower())
                if info:
                    source = f"{info['source']}_exact" if mt.lower() == info.get("canonical_name", "").lower() else f"{info['source']}_substring"
                    batch.append((row["id"], info["entity_id"], "subject", mt, source))
                    stats["subject_matches"] += 1
                    stats["mentions_found"] += 1
            # Object matches
            for m in pattern.finditer(obj):
                mt = m.group(1)
                info = lookup.get(mt.lower())
                if info:
                    source = f"{info['source']}_substring"
                    batch.append((row["id"], info["entity_id"], "object", mt, source))
                    stats["object_matches"] += 1
                    stats["mentions_found"] += 1

        log.info("Collected %d mention rows in %.1fs",
                 len(batch), time.time() - t0)

        if dry_run:
            log.info("DRY RUN — not writing")
        elif batch:
            log.info("Bulk inserting %d rows…", len(batch))
            with conn.cursor() as cur:
                # execute_values for efficiency
                psycopg2.extras.execute_values(
                    cur,
                    """INSERT INTO triple_entity_mentions
                       (triple_id, entity_id, role, match_text, match_source)
                       VALUES %s
                       ON CONFLICT DO NOTHING""",
                    batch,
                    template="(%s, %s, %s, %s, %s)",
                    page_size=2000,
                )
                stats["rows_inserted"] = cur.rowcount
            conn.commit()

        # Report
        log.info("=" * 60)
        log.info("EXPANSION COMPLETE%s", " (DRY RUN)" if dry_run else "")
        log.info("=" * 60)
        for k, v in stats.most_common():
            log.info("  %-28s %s", k, v)

        if not dry_run:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM triple_entity_mentions")
                total = cur.fetchone()["n"]
                cur.execute(
                    """SELECT role, COUNT(*) AS n FROM triple_entity_mentions GROUP BY role"""
                )
                by_role = cur.fetchall()
                cur.execute(
                    """SELECT ce.canonical_name, COUNT(*) AS mentions
                       FROM triple_entity_mentions tem
                       JOIN canonical_entities ce ON ce.id = tem.entity_id
                       GROUP BY ce.canonical_name
                       ORDER BY 2 DESC LIMIT 15"""
                )
                top = cur.fetchall()
            log.info("")
            log.info("triple_entity_mentions total: %s", total)
            for r in by_role:
                log.info("  role=%s: %s", r["role"], r["n"])
            log.info("")
            log.info("Top 15 entities by mention count:")
            for r in top:
                log.info("  %-35s %s", r["canonical_name"][:35], r["mentions"])
    finally:
        conn.close()


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--only-new", action="store_true",
                    help="Only scan triples with no existing mentions")
    ap.add_argument("--limit", type=int, default=None,
                    help="Limit triples scanned (for testing)")
    args = ap.parse_args()
    scan_triples(dry_run=args.dry_run, only_new=args.only_new, limit=args.limit)


if __name__ == "__main__":
    main()
