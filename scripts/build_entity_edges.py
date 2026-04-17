"""Tier 4 — Entity-to-entity edge synthesis.

Aggregates paper_claim_triples into an entity-to-entity graph with
support_count, mean_confidence, and operation_crossing flags. This is the
layer Discovery traverses: given seed entity "Cortisol," find all N-hop
paths to target "Longevity" through mechanistically coherent edges.

Edge identity: (source, predicate_type, target) where source/target is
either a canonical_entity UUID (high confidence) or a normalized string
(pending Tier 2 full normalization). Edges carry both:
  - Mechanistic specificity (predicate_type, raw predicate set)
  - Network signal (support_count = number of papers supporting this edge)
  - Cross-operation flag (the arbitrage signal per Pearl 2026-04-16)

Also unions in the curated kb_pathway_graph_edges as first-class edges so
backbone mechanistic detail sits alongside literature-derived edges.

Schema created on first run. Idempotent after that.

Usage:
    python scripts/build_entity_edges.py --dry-run
    python scripts/build_entity_edges.py                    # rebuild
    python scripts/build_entity_edges.py --min-support 2    # only edges with
                                                              >=2 supporting papers
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
log = logging.getLogger("build_entity_edges")

DB_HOST = os.environ.get("PGHOST", "Whits-Mac-mini.local")
DB_NAME = os.environ.get("PGDATABASE", "encoded_human")


# ---------------------------------------------------------------------------
# Schema — entity_edges + supporting paper map. Create if absent.
# ---------------------------------------------------------------------------
CREATE_ENTITY_EDGES = """
CREATE TABLE IF NOT EXISTS entity_edges (
    id                   BIGSERIAL PRIMARY KEY,
    source_entity_id     UUID REFERENCES canonical_entities(id) ON DELETE CASCADE,
    source_entity_name   TEXT NOT NULL,
    target_entity_id     UUID REFERENCES canonical_entities(id) ON DELETE CASCADE,
    target_entity_name   TEXT NOT NULL,
    predicate_type       TEXT NOT NULL,
    direction            TEXT,
    source_operation     TEXT,
    target_operation     TEXT,
    is_cross_operation   BOOLEAN GENERATED ALWAYS AS (
        source_operation IS NOT NULL
        AND target_operation IS NOT NULL
        AND source_operation <> target_operation
    ) STORED,
    support_count        INTEGER NOT NULL DEFAULT 0,
    supporting_paper_ids UUID[] NOT NULL DEFAULT '{}',
    mean_confidence      NUMERIC(4,3),
    max_confidence       NUMERIC(4,3),
    edge_source          TEXT NOT NULL,                -- 'literature' | 'backbone'
    pathway_id           TEXT,                          -- backbone: kb_pathways.id
    contradiction_load   INTEGER NOT NULL DEFAULT 0,    -- #supporting papers with 'contradicts' type
    created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at           TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS uq_entity_edges_identity
    ON entity_edges (
        md5(source_entity_name),
        predicate_type,
        md5(target_entity_name),
        COALESCE(pathway_id, 'lit')
    );

CREATE INDEX IF NOT EXISTS idx_entity_edges_source
    ON entity_edges (source_entity_id)
    WHERE source_entity_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entity_edges_target
    ON entity_edges (target_entity_id)
    WHERE target_entity_id IS NOT NULL;
CREATE INDEX IF NOT EXISTS idx_entity_edges_source_name
    ON entity_edges (lower(source_entity_name));
CREATE INDEX IF NOT EXISTS idx_entity_edges_target_name
    ON entity_edges (lower(target_entity_name));
CREATE INDEX IF NOT EXISTS idx_entity_edges_cross_op
    ON entity_edges (is_cross_operation) WHERE is_cross_operation = TRUE;
CREATE INDEX IF NOT EXISTS idx_entity_edges_support
    ON entity_edges (support_count DESC);
CREATE INDEX IF NOT EXISTS idx_entity_edges_pred_type
    ON entity_edges (predicate_type);
"""


def db_connect():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def ensure_schema(cur) -> None:
    cur.execute(CREATE_ENTITY_EDGES)


# ---------------------------------------------------------------------------
# Aggregation from paper_claim_triples
# ---------------------------------------------------------------------------
# Key insight (Pearl 2026-04-16): support_count = #distinct papers supporting
# this edge. Identity uses normalized lowercased entity string. When an entity
# has canonical_entity resolution, we prefer the canonical_name — otherwise
# fall back to the raw string.

AGGREGATE_FROM_TRIPLES = """
-- SPRINT G: aggregation now uses triple_entity_mentions to expand prose
-- objects into canonical-entity cross-products. A triple like
--   CCM1 → induces → "Oxidative stress and inflammatory response"
-- becomes TWO entity_edges:
--   CCM1 → induces → Oxidative stress
--   CCM1 → induces → Inflammation
-- because Oxidative stress AND Inflammation are both canonical entities
-- that appear as whole-word substrings in the object prose.
--
-- Coverage: a triple that has entity mentions on BOTH subject and object
-- side produces cross-product edges. Triples with no mentions on either
-- side fall through the expansion table and are NOT represented as edges
-- (they stay in paper_claim_triples as raw evidence for later discovery).
WITH resolved AS (
    -- Expansion-based pairs: use triple_entity_mentions to find every
    -- (subject_entity × object_entity) pairing per triple.
    SELECT
        pct.paper_id,
        pct.predicate_type,
        pct.direction,
        pct.primary_operation AS paper_operation,
        pct.confidence,
        s_ce.id                    AS source_entity_id,
        s_ce.canonical_name        AS source_entity_name,
        o_ce.id                    AS target_entity_id,
        o_ce.canonical_name        AS target_entity_name,
        s_ce.primary_operation     AS source_entity_op,
        o_ce.primary_operation     AS target_entity_op
    FROM paper_claim_triples pct
    JOIN triple_entity_mentions s_tem
      ON s_tem.triple_id = pct.id AND s_tem.role = 'subject'
    JOIN triple_entity_mentions o_tem
      ON o_tem.triple_id = pct.id AND o_tem.role = 'object'
    JOIN canonical_entities s_ce ON s_ce.id = s_tem.entity_id
    JOIN canonical_entities o_ce ON o_ce.id = o_tem.entity_id
    WHERE pct.predicate_type IS NOT NULL
      AND s_ce.id <> o_ce.id   -- no self-loops
),
triple_edges AS (
    SELECT
        (ARRAY_AGG(source_entity_id) FILTER (WHERE source_entity_id IS NOT NULL))[1] AS source_entity_id,
        source_entity_name,
        (ARRAY_AGG(target_entity_id) FILTER (WHERE target_entity_id IS NOT NULL))[1] AS target_entity_id,
        target_entity_name,
        predicate_type,
        MODE() WITHIN GROUP (ORDER BY direction)           AS direction,
        COALESCE(
            (ARRAY_AGG(source_entity_op) FILTER (WHERE source_entity_op IS NOT NULL))[1],
            MODE() WITHIN GROUP (ORDER BY paper_operation)
        )                                                  AS source_operation,
        COALESCE(
            (ARRAY_AGG(target_entity_op) FILTER (WHERE target_entity_op IS NOT NULL))[1],
            MODE() WITHIN GROUP (ORDER BY paper_operation)
        )                                                  AS target_operation,
        COUNT(DISTINCT paper_id)                           AS support_count,
        ARRAY_AGG(DISTINCT paper_id) FILTER (WHERE paper_id IS NOT NULL) AS supporting_paper_ids,
        AVG(confidence)                                    AS mean_confidence,
        MAX(confidence)                                    AS max_confidence,
        COUNT(DISTINCT paper_id) FILTER (
            WHERE predicate_type = 'blocks' OR direction = 'contradicts'
        )                                                  AS contradiction_load
    FROM resolved
    GROUP BY source_entity_name, target_entity_name, predicate_type
)
INSERT INTO entity_edges (
    source_entity_id, source_entity_name,
    target_entity_id, target_entity_name,
    predicate_type, direction,
    source_operation, target_operation,
    support_count, supporting_paper_ids,
    mean_confidence, max_confidence,
    contradiction_load, edge_source
)
SELECT
    source_entity_id, source_entity_name,
    target_entity_id, target_entity_name,
    predicate_type, direction,
    source_operation, target_operation,
    support_count, COALESCE(supporting_paper_ids, '{}'),
    mean_confidence, max_confidence,
    contradiction_load, 'literature'
FROM triple_edges
WHERE support_count >= %(min_support)s
ON CONFLICT (md5(source_entity_name), predicate_type, md5(target_entity_name), COALESCE(pathway_id, 'lit'))
DO UPDATE SET
    source_entity_id     = EXCLUDED.source_entity_id,
    target_entity_id     = EXCLUDED.target_entity_id,
    direction            = EXCLUDED.direction,
    source_operation     = EXCLUDED.source_operation,
    target_operation     = EXCLUDED.target_operation,
    support_count        = EXCLUDED.support_count,
    supporting_paper_ids = EXCLUDED.supporting_paper_ids,
    mean_confidence      = EXCLUDED.mean_confidence,
    max_confidence       = EXCLUDED.max_confidence,
    contradiction_load   = EXCLUDED.contradiction_load,
    updated_at           = NOW();
"""


# ---------------------------------------------------------------------------
# Import curated backbone edges (kb_pathway_graph_edges) as first-class edges.
# These are high-confidence, hand-curated mechanistic relationships.
# ---------------------------------------------------------------------------
IMPORT_BACKBONE_EDGES = """
WITH backbone AS (
    SELECT
        e.pathway_id,
        e.from_node, e.to_node,
        from_n.name AS source_entity_name,
        to_n.name   AS target_entity_name,
        from_ce.id  AS source_entity_id,
        to_ce.id    AS target_entity_id,
        -- Map backbone edge_type → paper_claim_triples predicate_type vocabulary
        CASE e.edge_type
            WHEN 'activates'      THEN 'activates'
            WHEN 'inhibits'       THEN 'inhibits'
            WHEN 'upregulates'    THEN 'upregulates'
            WHEN 'downregulates'  THEN 'downregulates'
            WHEN 'induces'        THEN 'induces'
            WHEN 'blocks'         THEN 'blocks'
            WHEN 'rescues'        THEN 'rescues'
            WHEN 'requires'       THEN 'requires'
            WHEN 'converts_to'    THEN 'is_upstream_of'
            WHEN 'transports'     THEN 'requires'
            WHEN 'secretes'       THEN 'is_upstream_of'
            WHEN 'binds'          THEN 'correlates_with'
            WHEN 'degrades'       THEN 'inhibits'
            ELSE                       'correlates_with'
        END AS predicate_type,
        CASE
            WHEN e.edge_type IN ('activates','inhibits','upregulates','downregulates','induces','blocks','rescues') THEN 'causal'
            WHEN e.edge_type IN ('converts_to','transports','is_upstream_of','is_downstream_of','requires') THEN 'mechanistic'
            ELSE 'associative'
        END AS direction,
        from_n.operation AS source_operation,
        to_n.operation   AS target_operation
    FROM kb_pathway_graph_edges e
    JOIN kb_pathway_graph_nodes from_n
      ON e.from_node = from_n.id AND e.pathway_id = from_n.pathway_id
    JOIN kb_pathway_graph_nodes to_n
      ON e.to_node = to_n.id AND e.pathway_id = to_n.pathway_id
    LEFT JOIN canonical_entities from_ce
      ON from_ce.canonical_name = from_n.name
    LEFT JOIN canonical_entities to_ce
      ON to_ce.canonical_name = to_n.name
)
INSERT INTO entity_edges (
    source_entity_id, source_entity_name,
    target_entity_id, target_entity_name,
    predicate_type, direction,
    source_operation, target_operation,
    support_count, supporting_paper_ids,
    mean_confidence, max_confidence,
    edge_source, pathway_id, contradiction_load
)
SELECT
    source_entity_id, source_entity_name,
    target_entity_id, target_entity_name,
    predicate_type, direction,
    source_operation, target_operation,
    1 AS support_count,          -- backbone is 1 curated edge per pathway
    '{}'::uuid[],
    1.0 AS mean_confidence,
    1.0 AS max_confidence,
    'backbone' AS edge_source,
    pathway_id, 0 AS contradiction_load
FROM backbone
ON CONFLICT (md5(source_entity_name), predicate_type, md5(target_entity_name), COALESCE(pathway_id, 'lit'))
DO UPDATE SET
    source_entity_id   = EXCLUDED.source_entity_id,
    target_entity_id   = EXCLUDED.target_entity_id,
    direction          = EXCLUDED.direction,
    source_operation   = EXCLUDED.source_operation,
    target_operation   = EXCLUDED.target_operation,
    mean_confidence    = EXCLUDED.mean_confidence,
    max_confidence     = EXCLUDED.max_confidence,
    updated_at         = NOW();
"""


def run(dry_run: bool, min_support: int) -> None:
    conn = db_connect()
    stats: Counter = Counter()
    try:
        with conn.cursor() as cur:
            # 1. Ensure schema
            log.info("Ensuring entity_edges schema…")
            ensure_schema(cur)

            if dry_run:
                # Count what WOULD be inserted
                cur.execute(
                    """
                    SELECT COUNT(*) AS n FROM (
                      SELECT 1 FROM paper_claim_triples pct
                      WHERE pct.subject IS NOT NULL AND pct.object IS NOT NULL
                        AND pct.predicate_type IS NOT NULL
                      GROUP BY pct.subject, pct.object, pct.predicate_type
                      HAVING COUNT(DISTINCT pct.paper_id) >= %s
                    ) x
                    """,
                    (min_support,),
                )
                would = cur.fetchone()["n"]
                log.info("DRY RUN: would write %s literature edges (min_support=%s)",
                         would, min_support)
                cur.execute(
                    "SELECT COUNT(*) AS n FROM kb_pathway_graph_edges"
                )
                bb = cur.fetchone()["n"]
                log.info("DRY RUN: would also write %s backbone edges", bb)
                conn.rollback()
                return

            # 2. Literature edges from paper_claim_triples
            #   Clear stale literature edges first — the expansion-based build
            #   produces canonical-only edges, so legacy prose-string edges
            #   from pre-Sprint-G builds need to be purged or they clutter the
            #   graph with dead-end nodes like "Perturbed progesterone
            #   signaling, blood-brain barrier dysfunction, vascular malformation".
            log.info("Clearing stale literature edges…")
            cur.execute("DELETE FROM entity_edges WHERE edge_source = 'literature'")
            stats["stale_literature_deleted"] = cur.rowcount

            log.info("Aggregating literature edges from paper_claim_triples (min_support=%s)…",
                     min_support)
            cur.execute(AGGREGATE_FROM_TRIPLES, {"min_support": min_support})
            stats["literature_edges_processed"] = cur.rowcount

            # 3. Backbone edges from kb_pathway_graph_edges
            log.info("Importing curated backbone edges…")
            cur.execute(IMPORT_BACKBONE_EDGES)
            stats["backbone_edges_processed"] = cur.rowcount

            conn.commit()

        # Verification queries
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM entity_edges")
            total = cur.fetchone()["n"]
            cur.execute(
                """SELECT edge_source, COUNT(*) AS n,
                          COUNT(CASE WHEN is_cross_operation THEN 1 END) AS cross_op
                   FROM entity_edges GROUP BY edge_source"""
            )
            src_breakdown = cur.fetchall()
            cur.execute(
                """SELECT predicate_type, COUNT(*) AS n
                   FROM entity_edges GROUP BY predicate_type ORDER BY n DESC LIMIT 15"""
            )
            pred_breakdown = cur.fetchall()
            cur.execute(
                """SELECT source_operation, target_operation, COUNT(*) AS n
                   FROM entity_edges
                   WHERE is_cross_operation = TRUE
                   GROUP BY 1,2 ORDER BY n DESC LIMIT 15"""
            )
            op_pairs = cur.fetchall()
            cur.execute(
                """SELECT source_entity_name, predicate_type, target_entity_name,
                          support_count, mean_confidence, source_operation, target_operation
                   FROM entity_edges
                   WHERE is_cross_operation = TRUE
                     AND support_count >= %s
                   ORDER BY support_count DESC LIMIT 15""",
                (min_support,),
            )
            top_cross = cur.fetchall()

        log.info("=" * 60)
        log.info("ENTITY EDGE SYNTHESIS COMPLETE")
        log.info("=" * 60)
        for k, v in stats.most_common():
            log.info("  %-35s %s", k, v)
        log.info("")
        log.info("TOTAL entity_edges:              %s", total)
        log.info("")
        log.info("BY SOURCE:")
        for r in src_breakdown:
            log.info("  %-12s  total=%d  cross_op=%d",
                     r["edge_source"], r["n"], r["cross_op"])
        log.info("")
        log.info("TOP PREDICATE TYPES:")
        for r in pred_breakdown:
            log.info("  %-20s %s", r["predicate_type"], r["n"])
        log.info("")
        log.info("TOP CROSS-OPERATION PAIRS:")
        for r in op_pairs:
            log.info("  %-14s → %-14s  n=%d", r["source_operation"], r["target_operation"], r["n"])
        log.info("")
        log.info("TOP CROSS-OPERATION EDGES (arbitrage candidates):")
        for r in top_cross:
            log.info("  [%s→%s] %s --[%s]--> %s  (support=%d, conf=%.2f)",
                     r["source_operation"] or "-", r["target_operation"] or "-",
                     r["source_entity_name"][:30], r["predicate_type"],
                     r["target_entity_name"][:30], r["support_count"],
                     float(r["mean_confidence"]) if r["mean_confidence"] else 0.0)
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--min-support", type=int, default=1,
                    help="Minimum distinct papers supporting an edge to include it")
    args = ap.parse_args()
    run(dry_run=args.dry_run, min_support=args.min_support)


if __name__ == "__main__":
    main()
