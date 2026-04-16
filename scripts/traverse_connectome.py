"""Tier 5 — Connectome traversal service.

Given a seed entity, traverses the entity_edges graph to find N-hop paths
and identifies arbitrage candidates (paths crossing many operation boundaries).

This is where the vision gets tested. The smoke test is:
    cortisol → pregnenolone → DHEA → T cells → longevity
— can the connectome reconstruct a known 5-hop chain with cross-operation edges?

Usage:
    # Smoke test: cortisol → longevity, up to 4 hops
    python scripts/traverse_connectome.py --seed Cortisol --target Longevity --max-hops 4

    # Discovery: all 3-hop paths from Cortisol that cross ≥2 operations
    python scripts/traverse_connectome.py --seed Cortisol --max-hops 3 --min-cross-ops 2

    # Missing-edge detector: entity pairs with cross-operation co-mention but no edge
    python scripts/traverse_connectome.py --missing-edges --seed AMPK
"""

from __future__ import annotations

import argparse
import logging
import os
from collections import Counter

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("traverse")

DB_HOST = os.environ.get("PGHOST", "Whits-Mac-mini.local")
DB_NAME = os.environ.get("PGDATABASE", "encoded_human")


def db_connect():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


# ---------------------------------------------------------------------------
# Recursive CTE traversal.
# Each hop extends the path by one edge; we track:
#   - full path of entity names
#   - path of edge predicate types (for display)
#   - set of operations touched (to count cross-operation hops)
#   - product of mean_confidence as path score
#   - sum of contradiction_load (penalty in scoring)
# ---------------------------------------------------------------------------
TRAVERSE_SQL = """
WITH RECURSIVE paths AS (
    -- Seed: all edges starting at the seed entity (case-insensitive name match)
    SELECT
        ARRAY[lower(source_entity_name), lower(target_entity_name)]               AS path_keys,
        ARRAY[source_entity_name, target_entity_name]                             AS path_names,
        ARRAY[predicate_type]                                                     AS preds,
        ARRAY[source_operation, target_operation]                                 AS ops,
        ARRAY[edge_source]                                                        AS edge_sources,
        ARRAY[support_count]                                                      AS supports,
        COALESCE(mean_confidence, 0.5)                                            AS path_conf,
        contradiction_load                                                        AS contra_load,
        1 AS hops
    FROM entity_edges
    WHERE lower(source_entity_name) = lower(%(seed)s)

    UNION ALL

    -- Extend: join on target→source
    SELECT
        p.path_keys || lower(e.target_entity_name),
        p.path_names || e.target_entity_name,
        p.preds || e.predicate_type,
        p.ops || e.target_operation,
        p.edge_sources || e.edge_source,
        p.supports || e.support_count,
        p.path_conf * COALESCE(e.mean_confidence, 0.5),
        p.contra_load + e.contradiction_load,
        p.hops + 1
    FROM paths p
    JOIN entity_edges e
      ON lower(e.source_entity_name) = p.path_keys[array_length(p.path_keys, 1)]
    WHERE p.hops < %(max_hops)s
      AND NOT (lower(e.target_entity_name) = ANY(p.path_keys))     -- prevent cycles
)
SELECT
    path_names, preds, ops, edge_sources, supports, path_conf, contra_load, hops,
    -- Count distinct operations crossed
    (SELECT COUNT(DISTINCT x) FROM UNNEST(ops) x WHERE x IS NOT NULL) AS distinct_ops,
    -- Count operation-boundary crossings (transitions where op changes)
    (SELECT COUNT(*)
        FROM UNNEST(ops) WITH ORDINALITY AS o(op, idx)
        WHERE idx > 1
          AND op IS NOT NULL
          AND op <> ops[idx-1]
          AND ops[idx-1] IS NOT NULL
    ) AS op_boundary_crossings
FROM paths
WHERE %(target)s IS NULL OR lower(path_names[array_length(path_names, 1)]) = lower(%(target)s)
ORDER BY
    CASE WHEN %(target)s IS NOT NULL THEN hops END ASC NULLS LAST,
    op_boundary_crossings DESC,
    path_conf DESC,
    contra_load ASC
LIMIT %(limit)s;
"""


def format_path(row: dict) -> str:
    names = row["path_names"]
    preds = row["preds"]
    ops = row["ops"]
    parts = []
    for i, n in enumerate(names):
        op = ops[i] if i < len(ops) else None
        op_tag = f"[{op[:3]}]" if op else "[?]"
        parts.append(f"{n} {op_tag}")
        if i < len(preds):
            parts.append(f"--{preds[i]}-->")
    return " ".join(parts)


def traverse(seed: str, target: str | None, max_hops: int,
             limit: int, min_cross_ops: int) -> None:
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(TRAVERSE_SQL, {
                "seed": seed, "target": target,
                "max_hops": max_hops, "limit": limit,
            })
            rows = cur.fetchall()

        log.info("=" * 72)
        log.info("CONNECTOME TRAVERSAL — seed='%s' target='%s' max_hops=%d",
                 seed, target or "(any)", max_hops)
        log.info("=" * 72)
        log.info("Paths found: %d", len(rows))

        filtered = [r for r in rows if r["op_boundary_crossings"] >= min_cross_ops]
        log.info("Paths with ≥%d operation-boundary crossings: %d",
                 min_cross_ops, len(filtered))
        log.info("")

        # Hop distribution
        hop_dist = Counter(r["hops"] for r in rows)
        log.info("HOP DISTRIBUTION:")
        for h in sorted(hop_dist):
            log.info("  %d hops: %d paths", h, hop_dist[h])
        log.info("")

        # Operation crossing stats
        cross_dist = Counter(r["op_boundary_crossings"] for r in rows)
        log.info("OPERATION-BOUNDARY CROSSING DISTRIBUTION:")
        for c in sorted(cross_dist):
            log.info("  %d crossings: %d paths", c, cross_dist[c])
        log.info("")

        # Top paths
        if filtered:
            log.info("TOP %d PATHS (by op_crossings, then confidence):",
                     min(20, len(filtered)))
            log.info("-" * 72)
            for i, r in enumerate(filtered[:20], 1):
                log.info("%2d. [hops=%d, cross=%d, conf=%.3f, contra=%d]",
                         i, r["hops"], r["op_boundary_crossings"],
                         float(r["path_conf"]),  r["contra_load"])
                log.info("    %s", format_path(r))
                log.info("    supports=%s sources=%s",
                         r["supports"], r["edge_sources"])
                log.info("")
        else:
            log.info("No paths match filter — relax --min-cross-ops or extend --max-hops")
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Missing-edge detector — Pearl's concept: pairs of entities with cross-operation
# co-mention but NO existing edge. These are the "arbitrage gap" candidates.
# ---------------------------------------------------------------------------
MISSING_EDGES_SQL = """
-- For each pair of entities co-mentioned in at least 2 papers but with no
-- direct edge between them, report as a candidate missing edge.
-- Only report pairs that would represent cross-operation bridges.
WITH co_mentions AS (
    SELECT
        LEAST(pct1.subject_normalized_id, pct2.subject_normalized_id)  AS ea,
        GREATEST(pct1.subject_normalized_id, pct2.subject_normalized_id) AS eb,
        COUNT(DISTINCT pct1.paper_id) AS co_paper_count
    FROM paper_claim_triples pct1
    JOIN paper_claim_triples pct2
      ON pct1.paper_id = pct2.paper_id
     AND pct1.subject_normalized_id < pct2.subject_normalized_id
    WHERE pct1.subject_normalized_id IS NOT NULL
      AND pct2.subject_normalized_id IS NOT NULL
    GROUP BY ea, eb
    HAVING COUNT(DISTINCT pct1.paper_id) >= 2
)
SELECT
    ce_a.canonical_name AS entity_a, ce_a.primary_operation AS op_a,
    ce_b.canonical_name AS entity_b, ce_b.primary_operation AS op_b,
    cm.co_paper_count
FROM co_mentions cm
JOIN canonical_entities ce_a ON ce_a.id::text = cm.ea
JOIN canonical_entities ce_b ON ce_b.id::text = cm.eb
LEFT JOIN entity_edges ee
  ON (ee.source_entity_id = ce_a.id AND ee.target_entity_id = ce_b.id)
  OR (ee.source_entity_id = ce_b.id AND ee.target_entity_id = ce_a.id)
WHERE ee.id IS NULL
  AND ce_a.primary_operation IS NOT NULL
  AND ce_b.primary_operation IS NOT NULL
  AND ce_a.primary_operation <> ce_b.primary_operation
  AND (%(seed)s IS NULL OR lower(ce_a.canonical_name) = lower(%(seed)s) OR lower(ce_b.canonical_name) = lower(%(seed)s))
ORDER BY cm.co_paper_count DESC
LIMIT 25;
"""


def missing_edges(seed: str | None) -> None:
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            cur.execute(MISSING_EDGES_SQL, {"seed": seed})
            rows = cur.fetchall()

        log.info("=" * 72)
        log.info("MISSING-EDGE DETECTOR%s",
                 f" (focus: {seed})" if seed else "")
        log.info("=" * 72)
        log.info("Candidates (entity pairs co-mentioned ≥2 papers, cross-operation, no edge):")
        log.info("")
        for r in rows:
            log.info("  [%s↔%s] %s ↔ %s  (co-mentions=%d)",
                     r["op_a"], r["op_b"],
                     r["entity_a"][:25], r["entity_b"][:25],
                     r["co_paper_count"])
        if not rows:
            log.info("  (none found — may need more normalized triples)")
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--seed", help="Entity to start traversal from")
    ap.add_argument("--target", help="Entity to reach (optional)")
    ap.add_argument("--max-hops", type=int, default=4,
                    help="Maximum path length (default 4)")
    ap.add_argument("--limit", type=int, default=100,
                    help="Max paths returned (default 100)")
    ap.add_argument("--min-cross-ops", type=int, default=0,
                    help="Minimum operation-boundary crossings (default 0)")
    ap.add_argument("--missing-edges", action="store_true",
                    help="Run the missing-edge detector")
    args = ap.parse_args()

    if args.missing_edges:
        missing_edges(seed=args.seed)
    else:
        if not args.seed:
            ap.error("--seed is required unless --missing-edges is set")
        traverse(
            seed=args.seed, target=args.target,
            max_hops=args.max_hops, limit=args.limit,
            min_cross_ops=args.min_cross_ops,
        )


if __name__ == "__main__":
    main()
