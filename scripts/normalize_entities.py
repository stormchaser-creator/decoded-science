"""Tier 2 — Entity normalization anchored to the backbone.

Resolve subject/object strings in paper_claim_triples to canonical_entities
by exact name or alias match (Pearl's rule: collapse strings, not biology).
Uncertain matches are left NULL — a known gap is better than a wrong link.

Also enriches canonical_entities.paper_count / triple_count / operation_distribution
from the actual data.

Usage:
    python scripts/normalize_entities.py --dry-run
    python scripts/normalize_entities.py
    python scripts/normalize_entities.py --expand-aliases    # learn new aliases
                                                               from high-support
                                                               near-matches

The strict mode (default) only matches exact normalized strings against
canonical_name or entries in the aliases array. Fuzzy / substring matching is
deliberately NOT used here — UMLS/MeSH resolution is Tier 3 work. This pass
answers: "Of the subjects/objects we already extracted, which resolve cleanly
to a backbone node?"
"""

from __future__ import annotations

import argparse
import logging
import os
import re
from collections import Counter, defaultdict

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("normalize_entities")

DB_HOST = os.environ.get("PGHOST", "Whits-Mac-mini.local")
DB_NAME = os.environ.get("PGDATABASE", "encoded_human")


# Lightweight string normalization — match Pearl's "collapse strings, not biology"
# - lowercase, strip, collapse internal whitespace
# - drop non-alphanumeric (except hyphen, digit, Greek characters)
# - no stemming, no synonyms beyond explicit aliases
_WS = re.compile(r"\s+")
_PUNCT = re.compile(r"[^\w\s\-αβγδεμκλνοπστφχψω]", flags=re.UNICODE)


def norm_key(s: str) -> str:
    if not s:
        return ""
    x = s.strip().lower()
    x = _PUNCT.sub(" ", x)
    x = _WS.sub(" ", x).strip()
    return x


def db_connect():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def build_lookup(cur) -> dict[str, str]:
    """Build {normalized_string: entity_id(uuid::text)} from canonical_entities."""
    cur.execute("SELECT id::text AS id, canonical_name, aliases FROM canonical_entities")
    lookup: dict[str, str] = {}
    clash: Counter = Counter()
    for row in cur.fetchall():
        keys = [row["canonical_name"]]
        if row["aliases"]:
            keys.extend(row["aliases"])
        for k in keys:
            nk = norm_key(k)
            if not nk:
                continue
            if nk in lookup and lookup[nk] != row["id"]:
                clash[nk] += 1
                # Keep first — a collision means two backbone nodes share an alias;
                # we prefer the first registration (usually the parent node)
                continue
            lookup[nk] = row["id"]
    if clash:
        log.warning("Alias collisions (first-wins): %d distinct strings map to >1 entity",
                    len(clash))
        for k, n in clash.most_common(5):
            log.warning("  '%s' seen %d times", k, n)
    log.info("Built lookup with %d normalized keys across canonical_entities", len(lookup))
    return lookup


def normalize_triples(cur, lookup: dict[str, str], dry_run: bool) -> Counter:
    stats: Counter = Counter()

    # Pull all triples that don't yet have normalization populated for at least one side
    cur.execute(
        """SELECT id, subject, object, subject_normalized_id, object_normalized_id
           FROM paper_claim_triples"""
    )
    rows = cur.fetchall()
    stats["total_rows"] = len(rows)

    # Batch update for speed
    updates: list[tuple[str | None, str | None, str]] = []  # (subj_id, obj_id, row_id)
    for row in rows:
        subj_key = norm_key(row["subject"])
        obj_key = norm_key(row["object"])
        subj_match = lookup.get(subj_key)
        obj_match = lookup.get(obj_key)

        cur_subj = row["subject_normalized_id"]
        cur_obj = row["object_normalized_id"]

        # Only update if we have something to set (or would change)
        new_subj = subj_match or cur_subj
        new_obj = obj_match or cur_obj
        if new_subj != cur_subj or new_obj != cur_obj:
            updates.append((new_subj, new_obj, row["id"]))

        if subj_match:
            stats["subject_resolved"] += 1
        if obj_match:
            stats["object_resolved"] += 1
        if subj_match and obj_match:
            stats["both_resolved"] += 1

    stats["rows_to_update"] = len(updates)

    if not dry_run and updates:
        psycopg2.extras.execute_batch(
            cur,
            "UPDATE paper_claim_triples SET subject_normalized_id=%s, object_normalized_id=%s WHERE id=%s",
            updates,
            page_size=500,
        )
    return stats


def refresh_canonical_stats(cur, dry_run: bool) -> Counter:
    """Update canonical_entities.paper_count / triple_count / operation_distribution
    from actual data in paper_claim_triples."""
    stats: Counter = Counter()

    if dry_run:
        # Just report, don't write
        cur.execute(
            """SELECT ent.canonical_name, ent.primary_operation,
                      COUNT(DISTINCT pct.paper_id) AS papers,
                      COUNT(*) AS triples
               FROM canonical_entities ent
               JOIN paper_claim_triples pct
                 ON (pct.subject_normalized_id = ent.id::text
                  OR pct.object_normalized_id  = ent.id::text)
               GROUP BY ent.id, ent.canonical_name, ent.primary_operation
               ORDER BY triples DESC LIMIT 20"""
        )
        rows = cur.fetchall()
        log.info("Top 20 entities by triple support (dry run):")
        for r in rows:
            log.info("  %-30s op=%-14s papers=%5d triples=%5d",
                     r["canonical_name"][:30], r["primary_operation"] or "-",
                     r["papers"], r["triples"])
        return stats

    # Compute paper_count + triple_count
    cur.execute(
        """
        WITH side_stats AS (
            SELECT ent.id AS entity_id,
                   COUNT(DISTINCT pct.paper_id) AS papers,
                   COUNT(*) AS triples
            FROM canonical_entities ent
            JOIN paper_claim_triples pct
              ON (pct.subject_normalized_id = ent.id::text
               OR pct.object_normalized_id  = ent.id::text)
            GROUP BY ent.id
        )
        UPDATE canonical_entities e
        SET paper_count = s.papers,
            triple_count = s.triples,
            updated_at = NOW()
        FROM side_stats s
        WHERE s.entity_id = e.id
        """
    )
    stats["entities_updated_counts"] = cur.rowcount

    # Compute operation_distribution from the triples where this entity appears
    # (uses the paper's primary_operation on paper_claim_triples)
    cur.execute(
        """
        WITH ops AS (
          SELECT ent.id AS entity_id,
                 pct.primary_operation AS op,
                 COUNT(*) AS n
          FROM canonical_entities ent
          JOIN paper_claim_triples pct
            ON (pct.subject_normalized_id = ent.id::text
             OR pct.object_normalized_id  = ent.id::text)
          WHERE pct.primary_operation IS NOT NULL
          GROUP BY ent.id, pct.primary_operation
        ),
        agg AS (
          SELECT entity_id, jsonb_object_agg(op, n) AS dist
          FROM ops GROUP BY entity_id
        )
        UPDATE canonical_entities e
        SET operation_distribution = a.dist,
            updated_at = NOW()
        FROM agg a
        WHERE a.entity_id = e.id
        """
    )
    stats["entities_updated_op_dist"] = cur.rowcount

    # Also compute a bridge_score: higher when entity participates in triples
    # crossing MANY different primary operations (the arbitrage signal)
    cur.execute(
        """
        WITH op_counts AS (
          SELECT ent.id AS entity_id,
                 COUNT(DISTINCT pct.primary_operation) AS n_ops,
                 COUNT(*) AS n_triples
          FROM canonical_entities ent
          JOIN paper_claim_triples pct
            ON (pct.subject_normalized_id = ent.id::text
             OR pct.object_normalized_id  = ent.id::text)
          WHERE pct.primary_operation IS NOT NULL
          GROUP BY ent.id
        )
        UPDATE canonical_entities e
        SET bridge_score = LEAST(1.0, (n_ops::numeric / 8.0) * LEAST(1.0, LN(1 + n_triples) / 10.0)),
            updated_at = NOW()
        FROM op_counts c
        WHERE c.entity_id = e.id
        """
    )
    stats["entities_scored"] = cur.rowcount

    return stats


def run(dry_run: bool) -> None:
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            lookup = build_lookup(cur)
            triple_stats = normalize_triples(cur, lookup, dry_run)

            log.info("")
            log.info("=" * 60)
            log.info("TRIPLE NORMALIZATION%s", " (DRY RUN)" if dry_run else "")
            log.info("=" * 60)
            for k, v in triple_stats.most_common():
                log.info("  %-30s %s", k, v)
            log.info("  subject hit rate: %.1f%%",
                     100.0 * triple_stats["subject_resolved"] / max(triple_stats["total_rows"], 1))
            log.info("  object hit rate: %.1f%%",
                     100.0 * triple_stats["object_resolved"] / max(triple_stats["total_rows"], 1))

            ce_stats = refresh_canonical_stats(cur, dry_run)

            if not dry_run:
                conn.commit()
                log.info("")
                log.info("CANONICAL_ENTITIES STATS REFRESH:")
                for k, v in ce_stats.most_common():
                    log.info("  %-30s %s", k, v)
            else:
                conn.rollback()

            # Final report
            cur.execute(
                """SELECT COUNT(*) AS total,
                          COUNT(subject_normalized_id) AS subj_norm,
                          COUNT(object_normalized_id) AS obj_norm,
                          COUNT(CASE WHEN subject_normalized_id IS NOT NULL
                                       AND object_normalized_id IS NOT NULL THEN 1 END) AS both
                   FROM paper_claim_triples"""
            )
            r = cur.fetchone()
            log.info("")
            log.info("FINAL paper_claim_triples STATE:")
            log.info("  total:              %s", r["total"])
            log.info("  subj resolved:      %s (%.1f%%)", r["subj_norm"],
                     100.0 * r["subj_norm"] / max(r["total"], 1))
            log.info("  obj resolved:       %s (%.1f%%)", r["obj_norm"],
                     100.0 * r["obj_norm"] / max(r["total"], 1))
            log.info("  both resolved:      %s (%.1f%%)", r["both"],
                     100.0 * r["both"] / max(r["total"], 1))

            # Show top bridge-score entities (arbitrage candidates)
            if not dry_run:
                cur.execute(
                    """SELECT canonical_name, primary_operation, paper_count,
                              triple_count, bridge_score
                       FROM canonical_entities
                       WHERE bridge_score IS NOT NULL
                       ORDER BY bridge_score DESC NULLS LAST
                       LIMIT 15"""
                )
                rows = cur.fetchall()
                log.info("")
                log.info("TOP BRIDGE ENTITIES (arbitrage candidates):")
                log.info("  %-30s %-14s %7s %7s %s", "entity", "operation", "papers", "triples", "bridge_score")
                for r2 in rows:
                    log.info("  %-30s %-14s %7d %7d %.3f",
                             r2["canonical_name"][:30], r2["primary_operation"] or "-",
                             r2["paper_count"] or 0, r2["triple_count"] or 0,
                             float(r2["bridge_score"]) if r2["bridge_score"] else 0.0)
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
