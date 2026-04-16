"""Harvest mechanism data from extraction_results.mechanisms JSONB into paper_claim_triples.

This is Tier 0.5 of the connectome build-out (per Eric + Pearl's 2026-04-16 sequencing):
turn the existing 74,376 mechanism records sitting in extraction_results.mechanisms JSONB
into typed triples in paper_claim_triples — Pearl's "gold-on-the-ground" insight. The
mechanism records already contain upstream_entity → interaction_type → downstream_entity;
this script maps them into the 14-value predicate_type taxonomy enforced by the
paper_claim_triples schema and persists them with operation tagging.

Idempotent via the unique index uq_pct_paper_triple on (paper_id, md5(subject), md5(predicate), md5(object)).

Usage:
    python scripts/harvest_mechanisms_to_triples.py --dry-run --limit 500
    python scripts/harvest_mechanisms_to_triples.py --limit 500           # real write, 500 mechanisms
    python scripts/harvest_mechanisms_to_triples.py                        # all mechanisms
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from collections import Counter
from typing import Any

import psycopg2
import psycopg2.extras
import psycopg2.errors

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("harvest_mechanisms")

# ---------------------------------------------------------------------------
# Predicate type mapping — mechanism interaction_type → paper_claim_triples.predicate_type
# (constrained to 14 values by paper_claim_triples_predicate_type_check)
#
# Pearl's taxonomy (2026-04-16): canonical buckets are ACTIVATES / INHIBITS /
# REGULATES / BINDS / CATALYZES. The schema only permits 14 values; we map raw
# interaction types into the closest semantic match. Raw predicate is preserved
# in the `predicate` column; the canonical bucket goes in `predicate_type`.
# ---------------------------------------------------------------------------
PREDICATE_MAP: dict[str, str] = {
    # Directional positive — activation
    "activates":        "activates",
    "upregulates":      "upregulates",
    "induces":          "induces",
    "triggers":         "induces",
    "causes":           "induces",
    "produces":         "induces",
    "releases":         "activates",
    "recruits":         "activates",
    "stabilizes":       "activates",
    "promotes":         "activates",
    "increases":        "upregulates",
    "enhances":         "upregulates",
    "enables":          "activates",
    "transcribes":      "activates",
    "translates":       "activates",
    "phosphorylates":   "activates",   # typical activating PTM
    # Directional negative — inhibition
    "inhibits":         "inhibits",
    "blocks":           "blocks",
    "downregulates":    "downregulates",
    "disrupts":         "inhibits",
    "impairs":          "inhibits",
    "damages":          "inhibits",
    "reduces":          "downregulates",
    "decreases":        "downregulates",
    "suppresses":       "inhibits",
    "sequesters":       "inhibits",
    "degrades":         "inhibits",
    "ubiquitinates":    "downregulates", # typical destabilizing PTM
    "cleaves":          "inhibits",       # typical proteolytic inactivation
    # Rescue
    "rescues":          "rescues",
    "restores":         "rescues",
    "compensates_for":  "compensates_for",
    "compensates":      "compensates_for",
    # Biomarker / prediction (ambiguous — treat as correlation by default)
    "is_biomarker_for": "is_biomarker_for",
    "predicts":         "predicts",
    "correlates_with":  "correlates_with",
    "associated_with":  "correlates_with",
    "linked_to":        "correlates_with",
    # Requirement / dependency
    "requires":         "requires",
    "depends_on":       "requires",
    # Upstream/downstream chain
    "is_upstream_of":   "is_upstream_of",
    "is_downstream_of": "is_downstream_of",
    # Ambiguous / association-only (Pearl: don't assume sign)
    "regulates":        "correlates_with",
    "modulates":        "correlates_with",
    "affects":          "correlates_with",
    "influences":       "correlates_with",
    "mediates":         "correlates_with",
    "interacts_with":   "correlates_with",
    "binds":            "correlates_with",
    "integrates":       "correlates_with",
    "other":            "correlates_with",
}

# Direction mapping — schema check is {causal, associative, mechanistic, descriptive}
CAUSAL_PREDICATE_TYPES = {"activates", "inhibits", "upregulates", "downregulates",
                          "induces", "blocks", "rescues"}
MECHANISTIC_PREDICATE_TYPES = {"is_upstream_of", "is_downstream_of", "requires",
                               "compensates_for"}
ASSOCIATIVE_PREDICATE_TYPES = {"correlates_with", "is_biomarker_for", "predicts"}


def direction_for(predicate_type: str) -> str:
    if predicate_type in CAUSAL_PREDICATE_TYPES:
        return "causal"
    if predicate_type in MECHANISTIC_PREDICATE_TYPES:
        return "mechanistic"
    if predicate_type in ASSOCIATIVE_PREDICATE_TYPES:
        return "associative"
    return "descriptive"


def clean_entity(s: Any) -> str | None:
    """Lightweight string-cleaning stub — Pearl said: don't attempt full normalization,
    leave that to Tier 2 with the backbone anchor. Just strip obvious noise."""
    if s is None:
        return None
    s = str(s).strip()
    if not s or s.lower() in {"null", "none", "n/a", "unknown"}:
        return None
    # Truncate extremely long entity strings (usually a sign of extraction drift
    # — the model returned a sentence instead of a noun)
    if len(s) > 200:
        return None
    return s


def normalize_predicate_raw(s: str) -> str:
    return (s or "").strip().lower().replace("-", "_").replace(" ", "_")


# ---------------------------------------------------------------------------
# DB connection
# ---------------------------------------------------------------------------
DB_HOST = os.environ.get("PGHOST", "Whits-Mac-mini.local")
DB_NAME = os.environ.get("PGDATABASE", "encoded_human")


def db_connect():
    return psycopg2.connect(
        host=DB_HOST,
        dbname=DB_NAME,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


# ---------------------------------------------------------------------------
# Harvester
# ---------------------------------------------------------------------------
SELECT_MECHANISMS_SQL = """
SELECT
    er.id            AS extraction_id,
    er.paper_id      AS paper_id,
    er.primary_operation AS paper_primary_operation,
    er.study_design  AS study_design,
    mech.ordinality  AS mech_idx,
    mech.value       AS mechanism
FROM extraction_results er
JOIN LATERAL jsonb_array_elements(er.mechanisms) WITH ORDINALITY AS mech(value, ordinality)
    ON TRUE
WHERE jsonb_array_length(er.mechanisms) > 0
ORDER BY er.created_at DESC
{limit_clause}
"""

INSERT_TRIPLE_SQL = """
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
SET edge_context = COALESCE(EXCLUDED.edge_context, paper_claim_triples.edge_context),
    context_type = COALESCE(EXCLUDED.context_type, paper_claim_triples.context_type),
    source_mechanism_index = COALESCE(EXCLUDED.source_mechanism_index, paper_claim_triples.source_mechanism_index)
RETURNING id;
"""


# Lightweight context-type classifier (Pearl 2026-04-16)
# Context strings in mechanisms are biological scope qualifiers — tissue, cell type,
# disease, condition, organism. Keep the classifier simple; don't over-engineer.
_TISSUE_KEYWORDS = {
    "brain", "liver", "kidney", "heart", "lung", "muscle", "gut", "intestine",
    "colon", "stomach", "bone", "skin", "blood", "tissue", "organ", "adipose",
    "pancreas", "spleen", "thymus", "lymph", "nerve", "retina", "cornea",
    "vasculature", "artery", "vein", "endothelium", "epithelium", "mucosa",
}
_CELL_TYPE_SUFFIXES = ("cyte", "blast", "cell", "cells", "neuron", "neurons",
                       "macrophage", "lymphocyte", "lymphocytes", "hepatocyte",
                       "hepatocytes", "osteoblast", "osteoclast", "fibroblast",
                       "myocyte", "astrocyte", "microglia")
_DISEASE_KEYWORDS = {
    "disease", "disorder", "syndrome", "cancer", "tumor", "tumour", "carcinoma",
    "adenoma", "diabetes", "diabetic", "alzheimer", "parkinson", "sclerosis",
    "fibrosis", "ischemia", "infarct", "stroke", "sepsis", "hypertension",
    "atherosclerosis", "nephropathy", "retinopathy", "neuropathy", "obesity",
    "inflammation", "inflammatory", "infection", "autoimmune",
}
_CONDITION_KEYWORDS = {
    "stress", "hypoxia", "starvation", "fasting", "exercise", "aging", "aged",
    "young", "pregnancy", "sleep", "wake", "cold", "heat",
}
_ORGANISM_KEYWORDS = {
    "human", "mouse", "mice", "rat", "rats", "zebrafish", "c. elegans",
    "drosophila", "primate", "monkey", "pig", "sheep", "dog", "cat",
}


def classify_context(ctx: str | None) -> str | None:
    """Classify a context string into a coarse type. Cheap keyword-based; can be
    refined later. Returns None for empty/unknown context."""
    if not ctx:
        return None
    s = ctx.strip().lower()
    if not s or s in {"null", "none", "n/a", "unknown"}:
        return None
    if any(kw in s for kw in _DISEASE_KEYWORDS):
        return "disease_state"
    if s.endswith(_CELL_TYPE_SUFFIXES):
        return "cell_type"
    if any(s.endswith(sfx) for sfx in _CELL_TYPE_SUFFIXES):
        return "cell_type"
    if any(kw in s for kw in _TISSUE_KEYWORDS):
        return "tissue"
    if any(kw in s for kw in _CONDITION_KEYWORDS):
        return "condition"
    if any(kw in s for kw in _ORGANISM_KEYWORDS):
        return "organism"
    return "unknown"

# Evidence type mapping from study_design
EVIDENCE_TYPE_MAP: dict[str, str] = {
    "rct":             "RCT",
    "randomized_controlled_trial": "RCT",
    "cohort":          "cohort",
    "case_control":    "case_control",
    "case-control":    "case_control",
    "in_vitro":        "in_vitro",
    "invitro":         "in_vitro",
    "computational":   "mechanistic",
    "animal":          "animal",
    "review":          "review",
    "systematic_review": "review",
    "meta_analysis":   "meta_analysis",
    "meta-analysis":   "meta_analysis",
    "mechanistic":     "mechanistic",
}


def evidence_type_for(study_design: str | None) -> str | None:
    if not study_design:
        return None
    key = study_design.strip().lower().replace(" ", "_").replace("-", "_")
    if key in EVIDENCE_TYPE_MAP:
        return EVIDENCE_TYPE_MAP[key]
    return None


def run_harvest(limit: int | None, dry_run: bool, sample_count: int = 20) -> None:
    conn = db_connect()
    stats = Counter()
    raw_predicates_seen: Counter = Counter()
    predicate_types_written: Counter = Counter()
    operation_types_written: Counter = Counter()
    samples_for_pearl: list[dict[str, Any]] = []

    try:
        with conn.cursor() as cur:
            limit_clause = f"LIMIT {limit}" if limit else ""
            sql = SELECT_MECHANISMS_SQL.format(limit_clause=limit_clause)
            cur.execute(sql)

            for row in cur.fetchall():
                mech: dict[str, Any] = row["mechanism"]
                stats["mechanisms_seen"] += 1

                subj = clean_entity(mech.get("upstream_entity"))
                obj = clean_entity(mech.get("downstream_entity"))
                raw_predicate = normalize_predicate_raw(
                    mech.get("interaction_type") or "")
                confidence = mech.get("confidence")

                if not subj or not obj:
                    stats["skipped_missing_entity"] += 1
                    continue
                if not raw_predicate:
                    stats["skipped_missing_predicate"] += 1
                    continue

                raw_predicates_seen[raw_predicate] += 1

                predicate_type = PREDICATE_MAP.get(raw_predicate)
                if predicate_type is None:
                    # Any predicate we haven't mapped falls through to correlates_with
                    predicate_type = "correlates_with"
                    stats["unmapped_predicates_as_correlates"] += 1

                direction = direction_for(predicate_type)
                primary_op = row.get("paper_primary_operation")
                evidence = evidence_type_for(row.get("study_design"))

                predicate_types_written[predicate_type] += 1
                if primary_op:
                    operation_types_written[primary_op] += 1

                edge_ctx = clean_entity(mech.get("context"))
                ctx_type = classify_context(edge_ctx)
                mech_idx = int(row["mech_idx"]) if row.get("mech_idx") is not None else None

                params = {
                    "paper_id": row["paper_id"],
                    "extraction_id": row["extraction_id"],
                    "subject": subj,
                    # Preserve raw predicate string for downstream context
                    "predicate": raw_predicate,
                    "object": obj,
                    "predicate_type": predicate_type,
                    "primary_operation": primary_op,
                    "evidence_type": evidence,
                    "confidence": confidence,
                    "direction": direction,
                    "edge_context": edge_ctx,
                    "context_type": ctx_type,
                    "source_mechanism_index": mech_idx,
                }

                if len(samples_for_pearl) < sample_count:
                    samples_for_pearl.append({
                        "subject": subj,
                        "predicate": raw_predicate,
                        "object": obj,
                        "predicate_type": predicate_type,
                        "direction": direction,
                        "primary_operation": primary_op,
                        "confidence": confidence,
                    })

                if dry_run:
                    stats["would_insert"] += 1
                    continue

                try:
                    cur.execute(INSERT_TRIPLE_SQL, params)
                    res = cur.fetchone()
                    if res:
                        stats["inserted"] += 1
                    else:
                        stats["duplicate_skipped"] += 1
                except psycopg2.errors.CheckViolation as e:
                    # Most likely: predicate_type, direction, or evidence_type
                    # violated the check constraint — log and continue
                    conn.rollback()
                    stats["check_constraint_violated"] += 1
                    log.warning(
                        "Check violation: predicate_type=%s direction=%s evidence=%s err=%s",
                        predicate_type, direction, evidence, e,
                    )
                    continue

            if not dry_run:
                conn.commit()

        # Output
        log.info("=" * 72)
        log.info("HARVEST SUMMARY%s", " (DRY RUN)" if dry_run else "")
        log.info("=" * 72)
        for k, v in stats.most_common():
            log.info("  %-35s %s", k, v)
        log.info("")
        log.info("PREDICATE TYPES WRITTEN (canonical, 14-value schema):")
        for k, v in predicate_types_written.most_common():
            log.info("  %-20s %s", k, v)
        log.info("")
        log.info("TOP RAW PREDICATES SEEN:")
        for k, v in raw_predicates_seen.most_common(15):
            log.info("  %-20s %s", k, v)
        log.info("")
        log.info("OPERATIONS TAGGED (via paper primary_operation):")
        for k, v in operation_types_written.most_common():
            log.info("  %-20s %s", k, v)

        log.info("")
        log.info("=" * 72)
        log.info("SAMPLE TRIPLES FOR PEARL REVIEW (first %d)", len(samples_for_pearl))
        log.info("=" * 72)
        for i, s in enumerate(samples_for_pearl, 1):
            op = s["primary_operation"] or "—"
            conf = f"{s['confidence']:.2f}" if s["confidence"] is not None else "—"
            log.info(
                "%2d. %s --[%s/%s/%s]--> %s  (op=%s, conf=%s)",
                i, s["subject"], s["predicate"], s["predicate_type"], s["direction"],
                s["object"], op, conf,
            )
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--limit", type=int, default=None,
                    help="Limit mechanisms processed. Omit for full harvest.")
    ap.add_argument("--dry-run", action="store_true",
                    help="Analyze but do not write rows.")
    ap.add_argument("--sample-count", type=int, default=20,
                    help="How many sample triples to print for review (default 20).")
    args = ap.parse_args()

    log.info("Starting harvest. limit=%s dry_run=%s", args.limit, args.dry_run)
    run_harvest(limit=args.limit, dry_run=args.dry_run, sample_count=args.sample_count)


if __name__ == "__main__":
    main()
