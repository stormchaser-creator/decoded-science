"""Harvest typed triples from the claims table into paper_claim_triples.

Complement to harvest_mechanisms_to_triples.py. The claims table has 25,633+
rows where subject/predicate/object are populated (from the post-session-49
extraction worker). This script reads those and writes them to
paper_claim_triples so the edge synthesizer can see claim-level evidence
alongside mechanism-level evidence.

Idempotent via the unique index uq_pct_paper_triple.

Usage:
    python scripts/harvest_claims_to_triples.py --dry-run
    python scripts/harvest_claims_to_triples.py
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
log = logging.getLogger("harvest_claims")

DB_HOST = os.environ.get("PGHOST", "Whits-Mac-mini.local")
DB_NAME = os.environ.get("PGDATABASE", "encoded_human")

# ---- Reuse the same predicate mapping as harvest_mechanisms_to_triples.py ----
# Kept inline here to avoid cross-script imports and for clarity.
# paper_claim_triples.predicate_type CHECK allows the 14 values below; anything
# else we map gets funneled to correlates_with (direction=associative).
PREDICATE_MAP: dict[str, str] = {
    # Directional positive
    "activates": "activates", "upregulates": "upregulates",
    "induces": "induces", "triggers": "induces", "causes": "induces",
    "produces": "induces", "releases": "activates", "recruits": "activates",
    "stabilizes": "activates", "promotes": "activates",
    "increases": "upregulates", "enhances": "upregulates",
    "enables": "activates", "phosphorylates": "activates",
    "transcribes": "activates", "translates": "activates",
    # Directional negative
    "inhibits": "inhibits", "blocks": "blocks",
    "downregulates": "downregulates", "disrupts": "inhibits",
    "impairs": "inhibits", "damages": "inhibits",
    "reduces": "downregulates", "decreases": "downregulates",
    "suppresses": "inhibits", "sequesters": "inhibits",
    "degrades": "inhibits", "cleaves": "inhibits",
    "ubiquitinates": "downregulates",
    # Rescue / compensation
    "rescues": "rescues", "restores": "rescues",
    "compensates_for": "compensates_for", "compensates": "compensates_for",
    # Biomarker / prediction / requirement
    "is_biomarker_for": "is_biomarker_for",
    "predicts": "predicts",
    "correlates_with": "correlates_with",
    "associated_with": "correlates_with",
    "linked_to": "correlates_with",
    "requires": "requires", "depends_on": "requires",
    "is_upstream_of": "is_upstream_of",
    "is_downstream_of": "is_downstream_of",
    # Ambiguous / association-only
    "regulates": "correlates_with", "modulates": "correlates_with",
    "affects": "correlates_with", "influences": "correlates_with",
    "mediates": "correlates_with", "interacts_with": "correlates_with",
    "binds": "correlates_with", "integrates": "correlates_with",
    "other": "correlates_with",
}

CAUSAL = {"activates", "inhibits", "upregulates", "downregulates",
          "induces", "blocks", "rescues"}
MECHANISTIC = {"is_upstream_of", "is_downstream_of", "requires", "compensates_for"}
ASSOCIATIVE = {"correlates_with", "is_biomarker_for", "predicts"}


def norm_predicate(s: str) -> str:
    return (s or "").strip().lower().replace("-", "_").replace(" ", "_")


def clean_entity(s):
    if s is None:
        return None
    s = str(s).strip()
    if not s or s.lower() in {"null", "none", "n/a", "unknown"}:
        return None
    if len(s) > 200:
        return None
    return s


def direction_for(predicate_type: str) -> str:
    if predicate_type in CAUSAL:
        return "causal"
    if predicate_type in MECHANISTIC:
        return "mechanistic"
    if predicate_type in ASSOCIATIVE:
        return "associative"
    return "descriptive"


def db_connect():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


SELECT_CLAIMS = """
SELECT c.id, c.paper_id, c.subject, c.predicate, c.object,
       c.operations, c.is_cross_operation,
       c.confidence, c.source_section, c.claim_type,
       er.id AS extraction_id,
       er.primary_operation AS paper_primary_operation,
       er.study_design
FROM claims c
LEFT JOIN LATERAL (
    SELECT id, primary_operation, study_design
    FROM extraction_results
    WHERE paper_id = c.paper_id
    ORDER BY created_at DESC
    LIMIT 1
) er ON TRUE
WHERE c.subject IS NOT NULL
  AND c.predicate IS NOT NULL
  AND c.object IS NOT NULL
"""

INSERT_TRIPLE = """
INSERT INTO paper_claim_triples (
    paper_id, extraction_id,
    subject, predicate, object,
    predicate_type, primary_operation,
    evidence_type, confidence, direction,
    edge_context, context_type, source_mechanism_index
) VALUES (
    %(paper_id)s, %(extraction_id)s,
    %(subject)s, %(predicate)s, %(object)s,
    %(predicate_type)s, %(primary_operation)s,
    %(evidence_type)s, %(confidence)s, %(direction)s,
    %(edge_context)s, %(context_type)s, %(source_mechanism_index)s
)
ON CONFLICT (paper_id, md5(subject), md5(predicate), md5(object)) DO UPDATE
SET confidence = COALESCE(EXCLUDED.confidence, paper_claim_triples.confidence),
    primary_operation = COALESCE(EXCLUDED.primary_operation, paper_claim_triples.primary_operation),
    evidence_type = COALESCE(EXCLUDED.evidence_type, paper_claim_triples.evidence_type)
RETURNING id;
"""

EVIDENCE_TYPE_MAP: dict[str, str] = {
    "rct": "RCT", "randomized_controlled_trial": "RCT",
    "cohort": "cohort", "case_control": "case_control",
    "in_vitro": "in_vitro", "computational": "mechanistic",
    "animal": "animal", "review": "review",
    "systematic_review": "review", "meta_analysis": "meta_analysis",
    "mechanistic": "mechanistic",
}


def evidence_for(sd):
    if not sd:
        return None
    k = sd.strip().lower().replace(" ", "_").replace("-", "_")
    return EVIDENCE_TYPE_MAP.get(k)


def run(dry_run: bool) -> None:
    conn = db_connect()
    stats: Counter = Counter()
    try:
        with conn.cursor() as cur:
            cur.execute(SELECT_CLAIMS)
            rows = cur.fetchall()
            stats["claims_seen"] = len(rows)

            for row in rows:
                subj = clean_entity(row["subject"])
                obj = clean_entity(row["object"])
                raw_pred = norm_predicate(row["predicate"])

                if not subj or not obj:
                    stats["skipped_missing_entity"] += 1
                    continue
                if not raw_pred:
                    stats["skipped_missing_predicate"] += 1
                    continue

                pt = PREDICATE_MAP.get(raw_pred, "correlates_with")
                if pt == "correlates_with" and raw_pred not in PREDICATE_MAP:
                    stats["unmapped_predicates"] += 1

                # Use the claim's OWN operations (from extraction) if available;
                # these are per-claim tags, more specific than paper-level primary_operation.
                # paper_claim_triples.primary_operation takes ONE value, so pick the first
                # from c.operations[] if present, else fall back to paper's primary_operation.
                claim_ops = row["operations"] or []
                primary_op = claim_ops[0] if claim_ops else row["paper_primary_operation"]

                params = {
                    "paper_id": row["paper_id"],
                    "extraction_id": row["extraction_id"],
                    "subject": subj,
                    "predicate": raw_pred,
                    "object": obj,
                    "predicate_type": pt,
                    "primary_operation": primary_op,
                    "evidence_type": evidence_for(row["study_design"]),
                    "confidence": row["confidence"],
                    "direction": direction_for(pt),
                    "edge_context": None,    # claims don't carry context like mechanisms do
                    "context_type": None,
                    "source_mechanism_index": None,
                }

                if dry_run:
                    stats["would_insert"] += 1
                    continue

                try:
                    cur.execute(INSERT_TRIPLE, params)
                    res = cur.fetchone()
                    if res:
                        stats["inserted_or_updated"] += 1
                except psycopg2.errors.CheckViolation as e:
                    conn.rollback()
                    stats["check_violation"] += 1
                    log.warning("Check violation: pt=%s dir=%s: %s",
                                pt, direction_for(pt), e)
                    continue

            if not dry_run:
                conn.commit()

        log.info("=" * 60)
        log.info("CLAIM HARVEST SUMMARY%s", " (DRY RUN)" if dry_run else "")
        log.info("=" * 60)
        for k, v in stats.most_common():
            log.info("  %-35s %s", k, v)

        if not dry_run:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(*) AS n FROM paper_claim_triples")
                log.info("")
                log.info("paper_claim_triples total rows now: %s",
                         cur.fetchone()["n"])
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    run(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
