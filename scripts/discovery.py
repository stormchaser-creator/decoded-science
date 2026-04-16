"""Sprint B — Discovery Pipeline.

Topic-in → scored hypothesis paths + weakest-edge gap flags.
The topic-to-thesis layer that sits on top of the connectome.

Pipeline:
  1. Resolve seed topic(s) to canonical entities (or raw strings)
  2. Recursive traversal across entity_edges
  3. Score each candidate path:
       composite = (novelty × coherence × plausibility)
                   / (1 + contradiction_load + refutation_density)
  4. Flag weakest edges → pearl_missing_edges for targeted scrape
  5. Persist run + scored paths
  6. (B5) Synthesize hypothesis brief from top-ranked path

CLI:
    python scripts/discovery.py init-schema
    python scripts/discovery.py run --seed Cortisol --target Longevity --max-hops 5
    python scripts/discovery.py run --seed "cavernous malformation" --max-hops 4
    python scripts/discovery.py list
    python scripts/discovery.py show --run-id <uuid>
    python scripts/discovery.py brief --run-id <uuid>
"""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import uuid
from collections import Counter

import psycopg2
import psycopg2.extras

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("discovery")

DB_HOST = os.environ.get("PGHOST", "Whits-Mac-mini.local")
DB_NAME = os.environ.get("PGDATABASE", "encoded_human")


def db_connect():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


# ============================================================================
# B1 — SCHEMA
# ============================================================================
SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS pearl_discovery_runs (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    seed_topic             TEXT NOT NULL,
    seed_entities          TEXT[] NOT NULL,
    target_entities        TEXT[],
    max_hops               INT NOT NULL DEFAULT 4,
    min_cross_ops          INT NOT NULL DEFAULT 0,
    status                 TEXT NOT NULL DEFAULT 'pending'
                           CHECK (status IN ('pending','generating','scoring','synthesizing',
                                             'complete','failed')),
    total_paths_considered INT DEFAULT 0,
    paths_scored           INT DEFAULT 0,
    weakest_edges_flagged  INT DEFAULT 0,
    hypothesis_brief_id    UUID,
    error_message          TEXT,
    metadata               JSONB DEFAULT '{}'::jsonb,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at           TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS pearl_path_scores (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                 UUID NOT NULL REFERENCES pearl_discovery_runs(id) ON DELETE CASCADE,
    rank                   INT NOT NULL,
    path_entity_names      TEXT[] NOT NULL,
    path_predicates        TEXT[] NOT NULL,
    path_operations        TEXT[] NOT NULL,
    path_edge_sources      TEXT[] NOT NULL,
    path_support_counts    INT[] NOT NULL,
    hops                   INT NOT NULL,
    op_boundary_crossings  INT NOT NULL DEFAULT 0,
    distinct_ops           INT NOT NULL DEFAULT 0,
    novelty_score          NUMERIC(5,4),
    coherence_score        NUMERIC(5,4),
    plausibility_score     NUMERIC(5,4),
    contradiction_load     NUMERIC(5,4),
    composite_score        NUMERIC(6,4),
    weakest_edge_idx       INT,
    weakest_edge_support   INT,
    flagged_for_scrape     BOOLEAN DEFAULT FALSE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_pps_run ON pearl_path_scores (run_id, rank);
CREATE INDEX IF NOT EXISTS idx_pps_composite ON pearl_path_scores (composite_score DESC);

CREATE TABLE IF NOT EXISTS pearl_hypothesis_briefs (
    id                     UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    run_id                 UUID NOT NULL REFERENCES pearl_discovery_runs(id) ON DELETE CASCADE,
    primary_path_id        UUID REFERENCES pearl_path_scores(id),
    thesis_statement       TEXT NOT NULL,
    mechanistic_narrative  TEXT,
    evidence_paper_ids     UUID[],
    evidence_paper_count   INT DEFAULT 0,
    gaps                   TEXT,
    falsification_criteria TEXT,
    related_path_ids       UUID[],
    exported_to_foundry    BOOLEAN DEFAULT FALSE,
    created_at             TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_phb_run ON pearl_hypothesis_briefs (run_id);
"""


def init_schema() -> None:
    conn = db_connect()
    with conn.cursor() as cur:
        cur.execute(SCHEMA_SQL)
    conn.commit()
    conn.close()
    log.info("Schema initialized: pearl_discovery_runs, pearl_path_scores, pearl_hypothesis_briefs")


# ============================================================================
# B2 — PATH GENERATOR (via recursive CTE on entity_edges)
# ============================================================================
# Same structure as traverse_connectome.py but returns all structured fields
# needed for scoring. Seeds may be canonical_entity names OR aliases OR raw
# strings that match existing entity_edges source_entity_name.
RESOLVE_SEED_SQL = """
WITH inputs AS (
    SELECT UNNEST(%s::text[]) AS seed
)
SELECT DISTINCT ce.canonical_name AS resolved_name
FROM inputs i
JOIN canonical_entities ce
    ON lower(ce.canonical_name) = lower(i.seed)
    OR lower(i.seed) = ANY(SELECT lower(a) FROM UNNEST(ce.aliases) a)
UNION
-- Seeds that don't resolve — still usable against raw entity_edges names
SELECT i.seed AS resolved_name
FROM inputs i
WHERE NOT EXISTS (
    SELECT 1 FROM canonical_entities ce
    WHERE lower(ce.canonical_name) = lower(i.seed)
       OR lower(i.seed) = ANY(SELECT lower(a) FROM UNNEST(ce.aliases) a)
) AND EXISTS (
    SELECT 1 FROM entity_edges ee
    WHERE lower(ee.source_entity_name) = lower(i.seed)
       OR lower(ee.target_entity_name) = lower(i.seed)
);
"""


TRAVERSE_PATHS_SQL = """
WITH RECURSIVE paths AS (
    SELECT
        ARRAY[lower(source_entity_name), lower(target_entity_name)]  AS path_keys,
        ARRAY[source_entity_name, target_entity_name]                AS path_names,
        ARRAY[predicate_type]                                        AS preds,
        ARRAY[source_operation, target_operation]                    AS ops,
        ARRAY[edge_source]                                           AS edge_sources,
        ARRAY[support_count]                                         AS supports,
        ARRAY[COALESCE(mean_confidence, 0.5)::numeric]               AS confs,
        contradiction_load                                           AS contra_load,
        1                                                            AS hops
    FROM entity_edges
    WHERE lower(source_entity_name) = ANY(%(seeds_lower)s)

    UNION ALL

    SELECT
        p.path_keys || lower(e.target_entity_name),
        p.path_names || e.target_entity_name,
        p.preds || e.predicate_type,
        p.ops || e.target_operation,
        p.edge_sources || e.edge_source,
        p.supports || e.support_count,
        p.confs || COALESCE(e.mean_confidence, 0.5)::numeric,
        p.contra_load + e.contradiction_load,
        p.hops + 1
    FROM paths p
    JOIN entity_edges e
        ON lower(e.source_entity_name) = p.path_keys[array_length(p.path_keys, 1)]
    WHERE p.hops < %(max_hops)s
      AND NOT (lower(e.target_entity_name) = ANY(p.path_keys))
)
SELECT path_names, preds, ops, edge_sources, supports, confs,
       contra_load, hops,
       (SELECT COUNT(DISTINCT x) FROM UNNEST(ops) x WHERE x IS NOT NULL)
           AS distinct_ops,
       (SELECT COUNT(*) FROM UNNEST(ops) WITH ORDINALITY AS o(op, idx)
          WHERE idx > 1 AND op IS NOT NULL AND op <> ops[idx-1] AND ops[idx-1] IS NOT NULL)
           AS op_boundary_crossings
FROM paths
WHERE (%(targets_lower)s IS NULL
       OR lower(path_names[array_length(path_names, 1)]) = ANY(%(targets_lower)s))
  AND hops >= %(min_hops)s
ORDER BY hops, contra_load ASC
LIMIT %(path_limit)s;
"""


# ============================================================================
# B3 — SCORING
# ============================================================================
# Pearl's formula (refined 2026-04-16):
#     score = (novelty × coherence × plausibility) / (1 + contra + refut)
#
# novelty:    1 - sigmoid(log(1 + endpoint_co_mentions / 10))
#             high when endpoints are RARELY discussed in same paper
# coherence:  (geomean of edge confidences) × (1 + 0.3 × op_boundary_crossings / hops)
# plausibility: fraction of edges grounded in backbone OR resolving to canonical_entity
# contradiction_load: per-path value from traversal, normalized
# refutation_density: placeholder 0.0 (would require explicit refutation extraction)

def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


def endpoint_co_mention_count(cur, source_name: str, target_name: str) -> int:
    """Papers that mention BOTH endpoints as subject/object of any triple."""
    cur.execute(
        """
        SELECT COUNT(DISTINCT p1.paper_id) AS n
        FROM paper_claim_triples p1
        JOIN paper_claim_triples p2 ON p1.paper_id = p2.paper_id
        WHERE (lower(p1.subject) = lower(%s) OR lower(p1.object) = lower(%s))
          AND (lower(p2.subject) = lower(%s) OR lower(p2.object) = lower(%s))
          AND p1.id <> p2.id
        """,
        (source_name, source_name, target_name, target_name),
    )
    return cur.fetchone()["n"]


def score_path(path: dict, endpoint_co_mentions: int) -> dict:
    confs = [float(c) for c in path["confs"]]
    supports = path["supports"]
    sources = path["edge_sources"]
    hops = path["hops"]
    op_crossings = path["op_boundary_crossings"]
    contra_raw = path["contra_load"]

    # Novelty: high when endpoints are rarely co-cited
    novelty = 1.0 - _sigmoid(math.log(1 + endpoint_co_mentions) - 2.0)
    # (when co_mentions = 0, novelty ≈ 0.88; when co_mentions = 100, novelty ≈ 0.12)

    # Coherence: geometric mean of confidences × op-crossing bonus
    if confs:
        geomean = math.exp(sum(math.log(max(c, 0.01)) for c in confs) / len(confs))
    else:
        geomean = 0.5
    op_bonus = 1.0 + 0.3 * (op_crossings / max(hops, 1))
    coherence = min(1.0, geomean * op_bonus)

    # Plausibility: fraction of edges that are backbone-grounded
    backbone_fraction = sum(1 for s in sources if s == "backbone") / max(len(sources), 1)
    plausibility = 0.5 + 0.5 * backbone_fraction

    # Contradiction load normalized (0-1)
    contra_norm = min(1.0, contra_raw / max(hops * 2, 1))

    # Composite
    denom = 1.0 + contra_norm + 0.0  # refutation_density placeholder
    composite = (novelty * coherence * plausibility) / denom

    # Weakest edge (lowest support)
    weakest_idx = supports.index(min(supports)) if supports else None
    weakest_support = min(supports) if supports else None

    return {
        "novelty": round(novelty, 4),
        "coherence": round(coherence, 4),
        "plausibility": round(plausibility, 4),
        "contradiction_load": round(contra_norm, 4),
        "composite": round(composite, 4),
        "weakest_edge_idx": weakest_idx,
        "weakest_edge_support": weakest_support,
    }


# ============================================================================
# B4 — ITERATION CONTROLLER (generate → score → flag gaps → persist)
# ============================================================================
def run_discovery(seed_topic: str, seeds: list[str], targets: list[str] | None,
                  max_hops: int, min_hops: int, path_limit: int,
                  min_cross_ops: int, keep_top: int) -> str:
    conn = db_connect()
    run_id = str(uuid.uuid4())
    try:
        with conn.cursor() as cur:
            # Persist run
            cur.execute(
                """INSERT INTO pearl_discovery_runs
                   (id, seed_topic, seed_entities, target_entities, max_hops,
                    min_cross_ops, status)
                   VALUES (%s, %s, %s, %s, %s, %s, 'generating')""",
                (run_id, seed_topic, seeds, targets, max_hops, min_cross_ops),
            )
            conn.commit()

            # Resolve seeds to canonical-or-raw names that exist in entity_edges
            cur.execute(RESOLVE_SEED_SQL, (seeds,))
            resolved_seeds = [r["resolved_name"] for r in cur.fetchall()]
            if not resolved_seeds:
                raise RuntimeError(
                    f"No seeds resolved. Tried: {seeds}. "
                    "Check canonical_entities / entity_edges for these names."
                )
            log.info("Resolved seeds → %s", resolved_seeds)

            # Targets (optional)
            resolved_targets = None
            if targets:
                cur.execute(RESOLVE_SEED_SQL, (targets,))
                resolved_targets = [r["resolved_name"] for r in cur.fetchall()]
                log.info("Resolved targets → %s", resolved_targets)

            # Traverse
            cur.execute(TRAVERSE_PATHS_SQL, {
                "seeds_lower": [s.lower() for s in resolved_seeds],
                "targets_lower": [t.lower() for t in resolved_targets] if resolved_targets else None,
                "max_hops": max_hops,
                "min_hops": min_hops,
                "path_limit": path_limit,
            })
            raw_paths = cur.fetchall()
            log.info("Traversal returned %d candidate paths", len(raw_paths))

            cur.execute(
                "UPDATE pearl_discovery_runs SET status='scoring', "
                "total_paths_considered=%s WHERE id=%s",
                (len(raw_paths), run_id),
            )
            conn.commit()

            # Filter by min_cross_ops BEFORE scoring (efficiency)
            paths = [p for p in raw_paths if p["op_boundary_crossings"] >= min_cross_ops]
            log.info("After min_cross_ops=%d filter: %d paths", min_cross_ops, len(paths))

            # Score
            scored = []
            co_mention_cache: dict[tuple[str, str], int] = {}
            for p in paths:
                endpoint_a = p["path_names"][0]
                endpoint_b = p["path_names"][-1]
                key = (endpoint_a.lower(), endpoint_b.lower())
                if key not in co_mention_cache:
                    co_mention_cache[key] = endpoint_co_mention_count(
                        cur, endpoint_a, endpoint_b)
                scores = score_path(p, co_mention_cache[key])
                scored.append({**p, **scores})

            scored.sort(key=lambda r: (r["composite"], -r["hops"]), reverse=True)
            top = scored[:keep_top]
            log.info("Keeping top %d of %d scored paths", len(top), len(scored))

            # Persist scored paths + flag weakest edges
            weakest_edge_set: set[tuple[str, str, str]] = set()
            for rank, p in enumerate(top, 1):
                score_row_id = str(uuid.uuid4())
                cur.execute(
                    """INSERT INTO pearl_path_scores
                       (id, run_id, rank, path_entity_names, path_predicates,
                        path_operations, path_edge_sources, path_support_counts,
                        hops, op_boundary_crossings, distinct_ops,
                        novelty_score, coherence_score, plausibility_score,
                        contradiction_load, composite_score,
                        weakest_edge_idx, weakest_edge_support)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
                               %s, %s, %s, %s, %s, %s, %s)""",
                    (
                        score_row_id, run_id, rank,
                        p["path_names"], p["preds"], p["ops"],
                        p["edge_sources"], p["supports"], p["hops"],
                        p["op_boundary_crossings"], p["distinct_ops"],
                        p["novelty"], p["coherence"], p["plausibility"],
                        p["contradiction_load"], p["composite"],
                        p["weakest_edge_idx"], p["weakest_edge_support"],
                    ),
                )

                # Flag weakest edge for scrape if support ≤ 1 and cross-op
                if p["weakest_edge_idx"] is not None and p["weakest_edge_support"] <= 1:
                    wi = p["weakest_edge_idx"]
                    src = p["path_names"][wi]
                    tgt = p["path_names"][wi + 1]
                    src_op = p["ops"][wi]
                    tgt_op = p["ops"][wi + 1] if wi + 1 < len(p["ops"]) else None
                    edge_key = (src.lower(), tgt.lower(), p["preds"][wi])
                    if (src_op and tgt_op and src_op != tgt_op
                            and edge_key not in weakest_edge_set):
                        weakest_edge_set.add(edge_key)
                        try:
                            cur.execute(
                                """INSERT INTO pearl_missing_edges
                                   (source_entity, target_entity, source_op, target_op,
                                    co_mention_count, detection_method, status, pearl_notes)
                                   VALUES (%s, %s, %s, %s, %s, 'discovery_weak_edge', 'candidate', %s)
                                   ON CONFLICT (source_entity, target_entity)
                                   DO UPDATE SET detection_method = 'discovery_weak_edge'
                                """,
                                (src, tgt, src_op, tgt_op, 1,
                                 f"Surfaced by discovery run {run_id[:8]} (path rank {rank}). "
                                 f"Support=1; predicate={p['preds'][wi]}. Candidate for targeted scrape."),
                            )
                            cur.execute(
                                "UPDATE pearl_path_scores SET flagged_for_scrape=TRUE WHERE id=%s",
                                (score_row_id,),
                            )
                        except psycopg2.errors.UniqueViolation:
                            conn.rollback()

            cur.execute(
                """UPDATE pearl_discovery_runs
                   SET status='complete',
                       paths_scored=%s,
                       weakest_edges_flagged=%s,
                       completed_at=NOW()
                   WHERE id=%s""",
                (len(top), len(weakest_edge_set), run_id),
            )
            conn.commit()

        log.info("=" * 60)
        log.info("DISCOVERY RUN COMPLETE — id=%s", run_id[:8])
        log.info("=" * 60)
        log.info("  seed_topic:              %s", seed_topic)
        log.info("  resolved seeds:          %s", resolved_seeds)
        log.info("  resolved targets:        %s", resolved_targets or "(any)")
        log.info("  paths considered:        %d", len(raw_paths))
        log.info("  paths scored + kept:     %d", len(top))
        log.info("  weakest edges flagged:   %d", len(weakest_edge_set))
        log.info("")

        if top:
            log.info("TOP %d PATHS:", min(10, len(top)))
            log.info("-" * 60)
            for i, p in enumerate(top[:10], 1):
                _print_path(i, p)
        return run_id
    except Exception as e:
        try:
            with conn.cursor() as cur:
                cur.execute(
                    "UPDATE pearl_discovery_runs SET status='failed', error_message=%s WHERE id=%s",
                    (str(e), run_id),
                )
            conn.commit()
        except Exception:
            pass
        raise
    finally:
        conn.close()


def _print_path(rank: int, p: dict) -> None:
    names = p["path_names"]
    preds = p["preds"]
    ops = p["ops"]
    supports = p["supports"]
    log.info("  %2d. [composite=%.3f | nov=%.3f coh=%.3f pla=%.3f con=%.3f | "
             "hops=%d cross=%d]",
             rank, float(p["composite"]), float(p["novelty"]),
             float(p["coherence"]), float(p["plausibility"]),
             float(p["contradiction_load"]), p["hops"],
             p["op_boundary_crossings"])
    parts = []
    for i, n in enumerate(names):
        op = ops[i] if i < len(ops) else None
        parts.append(f"{n}[{op[:3] if op else '?'}]")
        if i < len(preds):
            sup = supports[i] if i < len(supports) else "?"
            parts.append(f"--{preds[i]}/{sup}-->")
    log.info("      %s", " ".join(parts))


def list_runs() -> None:
    conn = db_connect()
    with conn.cursor() as cur:
        cur.execute(
            """SELECT id, seed_topic, status, total_paths_considered, paths_scored,
                      weakest_edges_flagged, created_at
               FROM pearl_discovery_runs ORDER BY created_at DESC LIMIT 20"""
        )
        rows = cur.fetchall()
    conn.close()
    log.info("%-10s %-30s %-12s %7s %7s %7s %s",
             "id", "seed_topic", "status", "considered", "scored", "flagged", "created")
    for r in rows:
        log.info("%-10s %-30s %-12s %7d %7d %7d %s",
                 str(r["id"])[:8],
                 (r["seed_topic"] or "")[:30],
                 r["status"],
                 r["total_paths_considered"] or 0,
                 r["paths_scored"] or 0,
                 r["weakest_edges_flagged"] or 0,
                 r["created_at"].strftime("%Y-%m-%d %H:%M") if r["created_at"] else "")


def show_run(run_id: str) -> None:
    conn = db_connect()
    with conn.cursor() as cur:
        cur.execute("SELECT * FROM pearl_discovery_runs WHERE id::text LIKE %s",
                    (run_id + "%",))
        run = cur.fetchone()
        if not run:
            log.info("No run found for id prefix '%s'", run_id)
            return
        cur.execute(
            """SELECT * FROM pearl_path_scores
               WHERE run_id=%s ORDER BY rank LIMIT 10""",
            (run["id"],),
        )
        paths = cur.fetchall()
    conn.close()

    log.info("RUN %s", run["id"])
    log.info("  seed_topic:          %s", run["seed_topic"])
    log.info("  seed_entities:       %s", run["seed_entities"])
    log.info("  target_entities:     %s", run["target_entities"])
    log.info("  max_hops:            %s", run["max_hops"])
    log.info("  status:              %s", run["status"])
    log.info("  paths considered:    %s", run["total_paths_considered"])
    log.info("  paths scored:        %s", run["paths_scored"])
    log.info("  weakest flagged:     %s", run["weakest_edges_flagged"])
    log.info("")
    for p in paths:
        d = {
            "composite": p["composite_score"], "novelty": p["novelty_score"],
            "coherence": p["coherence_score"], "plausibility": p["plausibility_score"],
            "contradiction_load": p["contradiction_load"],
            "hops": p["hops"], "op_boundary_crossings": p["op_boundary_crossings"],
            "path_names": p["path_entity_names"], "preds": p["path_predicates"],
            "ops": p["path_operations"], "supports": p["path_support_counts"],
        }
        _print_path(p["rank"], d)


# ============================================================================
# CLI
# ============================================================================
def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("init-schema", help="Create pearl_discovery_* tables")

    r = sub.add_parser("run", help="Run a discovery")
    r.add_argument("--seed", required=True, action="append",
                   help="Seed entity (can repeat)")
    r.add_argument("--target", action="append", default=None,
                   help="Target entity (optional, can repeat)")
    r.add_argument("--topic", default=None,
                   help="Topic description (defaults to first seed)")
    r.add_argument("--max-hops", type=int, default=4)
    r.add_argument("--min-hops", type=int, default=1)
    r.add_argument("--path-limit", type=int, default=500,
                   help="Max candidate paths to score (before top-K selection)")
    r.add_argument("--min-cross-ops", type=int, default=0)
    r.add_argument("--keep-top", type=int, default=25,
                   help="How many top-scored paths to persist")

    sub.add_parser("list", help="List recent discovery runs")

    sh = sub.add_parser("show", help="Show a run")
    sh.add_argument("--run-id", required=True)

    b = sub.add_parser("brief", help="Generate hypothesis brief from top path of a run")
    b.add_argument("--run-id", required=True)
    b.add_argument("--path-rank", type=int, default=1,
                   help="Which path rank to use (default 1 = top)")
    b.add_argument("--output", default=None,
                   help="Optional markdown file to write; default prints to stdout")

    args = ap.parse_args()

    if args.cmd == "init-schema":
        init_schema()
    elif args.cmd == "run":
        topic = args.topic or args.seed[0]
        run_discovery(
            seed_topic=topic,
            seeds=args.seed,
            targets=args.target,
            max_hops=args.max_hops,
            min_hops=args.min_hops,
            path_limit=args.path_limit,
            min_cross_ops=args.min_cross_ops,
            keep_top=args.keep_top,
        )
    elif args.cmd == "list":
        list_runs()
    elif args.cmd == "show":
        show_run(args.run_id)
    elif args.cmd == "brief":
        generate_brief(run_id=args.run_id, path_rank=args.path_rank,
                       output_path=args.output)


# ============================================================================
# B5 — HYPOTHESIS BRIEF GENERATOR
# ============================================================================
# Template-based synthesis. Pulls the selected path's edges, retrieves
# supporting paper IDs + titles, and assembles a structured brief.
# The brief is what Foundry will ingest as a thesis with evidence chain.
# ============================================================================

BRIEF_PREDICATE_NARRATIVE = {
    "activates":        "activates",
    "inhibits":         "inhibits",
    "upregulates":      "upregulates expression of",
    "downregulates":    "downregulates expression of",
    "induces":          "induces",
    "blocks":           "blocks",
    "rescues":          "rescues",
    "requires":         "requires",
    "is_upstream_of":   "is upstream of",
    "is_downstream_of": "is downstream of",
    "compensates_for":  "compensates for",
    "correlates_with":  "correlates with",
    "is_biomarker_for": "serves as a biomarker for",
    "predicts":         "predicts",
}


def _parse_uuid_array(val) -> list[str]:
    """psycopg2 returns uuid[] as raw PG array literal string '{u1,u2,...}'.
    Parse it into a Python list of string UUIDs."""
    if val is None:
        return []
    if isinstance(val, list):
        return [str(v) for v in val]
    s = str(val).strip()
    if s.startswith("{") and s.endswith("}"):
        inner = s[1:-1]
        if not inner:
            return []
        return [u.strip() for u in inner.split(",")]
    return []


def _get_edge(cur, src: str, tgt: str, predicate_type: str) -> dict | None:
    cur.execute(
        """SELECT e.*, ce_s.semantic_level AS src_level,
                  ce_t.semantic_level AS tgt_level
           FROM entity_edges e
           LEFT JOIN canonical_entities ce_s ON ce_s.id = e.source_entity_id
           LEFT JOIN canonical_entities ce_t ON ce_t.id = e.target_entity_id
           WHERE lower(e.source_entity_name) = lower(%s)
             AND lower(e.target_entity_name) = lower(%s)
             AND e.predicate_type = %s
           ORDER BY e.support_count DESC LIMIT 1""",
        (src, tgt, predicate_type),
    )
    return cur.fetchone()


def _paper_titles(cur, paper_ids: list) -> list[dict]:
    if not paper_ids:
        return []
    cur.execute(
        """SELECT id, title, journal, published_date, pub_year
           FROM raw_papers WHERE id = ANY(%s::uuid[]) LIMIT 20""",
        (paper_ids,),
    )
    return list(cur.fetchall())


def generate_brief(run_id: str, path_rank: int = 1,
                   output_path: str | None = None) -> None:
    conn = db_connect()
    try:
        with conn.cursor() as cur:
            # Load run
            cur.execute(
                "SELECT * FROM pearl_discovery_runs WHERE id::text LIKE %s",
                (run_id + "%",),
            )
            run = cur.fetchone()
            if not run:
                log.error("No run matching '%s'", run_id)
                return

            # Load target path
            cur.execute(
                """SELECT * FROM pearl_path_scores
                   WHERE run_id=%s AND rank=%s""",
                (run["id"], path_rank),
            )
            path = cur.fetchone()
            if not path:
                log.error("No path at rank %d for run %s", path_rank, run_id)
                return

            # Resolve each edge back to entity_edges to retrieve supporting papers
            names = path["path_entity_names"]
            preds = path["path_predicates"]
            ops   = path["path_operations"]
            edge_rows = []
            all_paper_ids: set = set()
            for i in range(len(preds)):
                row = _get_edge(cur, names[i], names[i + 1], preds[i])
                edge_rows.append(row)
                if row and row.get("supporting_paper_ids"):
                    all_paper_ids.update(_parse_uuid_array(row["supporting_paper_ids"]))

            papers = _paper_titles(cur, list(all_paper_ids)) if all_paper_ids else []

            # Related paths
            cur.execute(
                """SELECT id, rank, path_entity_names, composite_score
                   FROM pearl_path_scores
                   WHERE run_id=%s AND rank <= 10 AND rank <> %s
                   ORDER BY rank LIMIT 6""",
                (run["id"], path_rank),
            )
            related = cur.fetchall()

            # Build thesis
            thesis = _build_thesis(names, preds, ops)
            narrative = _build_narrative(names, preds, ops, edge_rows)
            gaps = _build_gaps(path, edge_rows, names, preds)
            falsification = _build_falsification(names, preds, ops, edge_rows)

            # Persist brief
            brief_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO pearl_hypothesis_briefs
                   (id, run_id, primary_path_id, thesis_statement, mechanistic_narrative,
                    evidence_paper_ids, evidence_paper_count, gaps,
                    falsification_criteria, related_path_ids)
                   VALUES (%s, %s, %s, %s, %s, %s::uuid[], %s, %s, %s, %s::uuid[])""",
                (brief_id, run["id"], path["id"], thesis, narrative,
                 list(all_paper_ids), len(all_paper_ids), gaps, falsification,
                 [str(r["id"]) for r in related]),
            )
            cur.execute(
                "UPDATE pearl_discovery_runs SET hypothesis_brief_id=%s WHERE id=%s",
                (brief_id, run["id"]),
            )
        conn.commit()

        # Render markdown
        md = _render_markdown(run, path, thesis, narrative, gaps,
                              falsification, papers, related, edge_rows)
        if output_path:
            with open(output_path, "w") as f:
                f.write(md)
            log.info("Brief saved to %s", output_path)
        else:
            print(md)
        log.info("brief_id=%s", brief_id[:8])
    finally:
        conn.close()


def _build_thesis(names, preds, ops) -> str:
    endpoint_a = names[0]
    endpoint_b = names[-1]
    # Identify cross-operation transitions
    ops_chain = [o for o in ops if o]
    unique_ops = []
    for o in ops_chain:
        if not unique_ops or unique_ops[-1] != o:
            unique_ops.append(o)
    ops_str = " → ".join(unique_ops) if unique_ops else "multiple operations"
    predicate_summary = _summarize_predicates(preds)
    return (
        f"{endpoint_a} is mechanistically linked to {endpoint_b} through a "
        f"{len(preds)}-hop cascade ({ops_str}) in which {endpoint_a.lower()} "
        f"{predicate_summary} {endpoint_b.lower()}."
    )


def _summarize_predicates(preds: list[str]) -> str:
    # Reduce the predicate chain to a coarse direction
    pos = {"activates", "upregulates", "induces", "is_upstream_of"}
    neg = {"inhibits", "blocks", "downregulates", "is_downstream_of"}
    pos_n = sum(1 for p in preds if p in pos)
    neg_n = sum(1 for p in preds if p in neg)
    if pos_n > neg_n:
        return "drives changes that ultimately influence"
    if neg_n > pos_n:
        return "disrupts a cascade that modulates"
    return "is associated with changes in"


def _build_narrative(names, preds, ops, edge_rows) -> str:
    lines = []
    for i in range(len(preds)):
        src = names[i]
        tgt = names[i + 1]
        pred = preds[i]
        pred_nat = BRIEF_PREDICATE_NARRATIVE.get(pred, pred)
        op_src = ops[i] if i < len(ops) and ops[i] else "?"
        op_tgt = ops[i + 1] if (i + 1) < len(ops) and ops[i + 1] else "?"
        er = edge_rows[i] or {}
        support = er.get("support_count", "?")
        conf = er.get("mean_confidence")
        source = er.get("edge_source", "?")
        conf_str = f"{float(conf):.2f}" if conf is not None else "n/a"
        line = (
            f"{i+1}. **{src}** ({op_src}) {pred_nat} **{tgt}** ({op_tgt}). "
            f"Evidence: {support} supporting paper(s), "
            f"confidence {conf_str}, source: {source}."
        )
        lines.append(line)
    return "\n".join(lines)


def _build_gaps(path, edge_rows, names, preds) -> str:
    weakest_idx = path["weakest_edge_idx"]
    weakest_support = path["weakest_edge_support"]
    lines = []
    if weakest_idx is not None:
        src = names[weakest_idx]
        tgt = names[weakest_idx + 1]
        pred = preds[weakest_idx]
        lines.append(
            f"Weakest link (hop #{weakest_idx + 1}): **{src} --{pred}--> {tgt}** "
            f"with only {weakest_support} supporting paper(s). Targeted scrape "
            f"recommended to confirm this edge."
        )
    # Any other support=1 edges?
    other_weak = []
    for i, er in enumerate(edge_rows):
        if i == weakest_idx or not er:
            continue
        if er.get("support_count", 99) <= 1:
            other_weak.append(
                f"- Hop #{i + 1}: {names[i]} --{preds[i]}--> {names[i + 1]} "
                f"(support={er.get('support_count')})"
            )
    if other_weak:
        lines.append("Additional low-support edges:")
        lines.extend(other_weak)
    if not lines:
        lines.append("All edges in this path have multi-paper support.")
    return "\n".join(lines)


def _build_falsification(names, preds, ops, edge_rows) -> str:
    return (
        f"This hypothesis predicts that interventions which disrupt any of the "
        f"{len(preds)} intermediate edges would abolish the {names[0]} → {names[-1]} "
        f"relationship. Specific falsification criteria:\n"
        f"1. If the {preds[0]} relationship between {names[0]} and {names[1]} is "
        f"not observed under replication, the chain entry is invalid.\n"
        f"2. If the terminal edge ({names[-2]} {preds[-1]} {names[-1]}) is refuted "
        f"in independent studies, the cascade does not reach {names[-1]}.\n"
        f"3. Intervention on any middle node (e.g., pharmacological inhibition of "
        f"cross-operation bridges) should alter the {names[-1]} outcome if the "
        f"cascade is causal; no change would refute the path."
    )


def _render_markdown(run, path, thesis, narrative, gaps, falsification,
                     papers, related, edge_rows) -> str:
    m: list[str] = []
    m.append(f"# Hypothesis Brief — Run {str(run['id'])[:8]}\n")
    m.append(f"**Seed topic:** {run['seed_topic']}\n")
    if run["target_entities"]:
        m.append(f"**Target:** {', '.join(run['target_entities'])}\n")
    m.append("")
    m.append("## Thesis")
    m.append(thesis)
    m.append("")
    m.append("## Scoring")
    m.append(f"- Composite score: **{float(path['composite_score']):.3f}**")
    m.append(f"- Novelty: {float(path['novelty_score']):.3f} "
             f"(lower = endpoints are commonly co-cited)")
    m.append(f"- Coherence: {float(path['coherence_score']):.3f} "
             f"(higher = confident edges across operations)")
    m.append(f"- Plausibility: {float(path['plausibility_score']):.3f} "
             f"(0.5 = all literature, 1.0 = all backbone)")
    m.append(f"- Contradiction load: {float(path['contradiction_load']):.3f}")
    m.append(f"- Hops: {path['hops']} | Operation-boundary crossings: "
             f"{path['op_boundary_crossings']} | Distinct ops: {path['distinct_ops']}")
    m.append("")
    m.append("## Mechanistic Chain")
    m.append(narrative)
    m.append("")
    m.append("## Evidence")
    m.append(f"- Supporting papers (union across all edges): **{len(papers)}**")
    for p in papers[:8]:
        year = p.get("pub_year") or ""
        m.append(f"  - *{(p.get('title') or '')[:110]}* "
                 f"({(p.get('journal') or '')[:40]}, {year})")
    if len(papers) > 8:
        m.append(f"  - …and {len(papers) - 8} more")
    m.append("")
    m.append("## Gaps / Low-Support Edges")
    m.append(gaps)
    m.append("")
    m.append("## Falsification Criteria")
    m.append(falsification)
    if related:
        m.append("")
        m.append("## Alternative Paths (same run)")
        for r in related:
            names = r["path_entity_names"]
            m.append(f"- Rank #{r['rank']} (composite {float(r['composite_score']):.3f}): "
                     f"{' → '.join(names)}")
    m.append("")
    m.append(f"---\n_Generated by Decoded Discovery pipeline. "
             f"Run id: {run['id']}_\n")
    return "\n".join(m)


if __name__ == "__main__":
    main()
