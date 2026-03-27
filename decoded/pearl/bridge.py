"""Pearl extraction bridge — writes Decoded paper extractions to Pearl's kb_entries.

When a paper is extracted in Decoded, this module bridges the structured
data into Pearl's Knowledge Base as kb_entries, making scientific evidence
directly available during Pearl facilitation sessions.

Mapping:
  Claims (causal)      → operation: Conduction   (cause→effect signal flow)
  Claims (mechanistic) → operation: Transduction  (mechanism = transformation)
  Claims (associative) → operation: Reception     (pattern/association detection)
  Claims (null)        → operation: Synthesis     (negative evidence)
  Mechanisms           → operation: Transduction
  Key findings         → operation: Synthesis

Density:
  strong evidence → spirit  (highest density, most certain)
  moderate        → mind
  weak / unknown  → body
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from typing import Any

import psycopg2
import psycopg2.extras

logger = logging.getLogger("decoded.pearl.bridge")

# Map from Decoded claim types to Pearl KB operations
_CLAIM_OP_MAP = {
    "causal":       "Conduction",
    "mechanistic":  "Transduction",
    "associative":  "Reception",
    "null":         "Synthesis",
    "correlative":  "Reception",
    "descriptive":  "Synthesis",
}

# Map from evidence strength to Pearl density
_DENSITY_MAP = {
    "strong":   "spirit",
    "moderate": "mind",
    "weak":     "body",
}


def _get_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    psycopg2.extras.register_uuid(conn)
    return conn


def bridge_extraction_to_pearl(
    result: Any,
    paper_meta: dict,
    conn=None,
) -> dict[str, int]:
    """Write extraction result into Pearl's kb_entries.

    Args:
        result: ExtractionResult object
        paper_meta: dict with title, doi, journal, published_date, authors
        conn: optional existing DB connection (if None, opens one)

    Returns:
        stats dict: {"claims": N, "mechanisms": N, "findings": N, "total": N}
    """
    own_conn = conn is None
    if own_conn:
        conn = _get_conn()

    cur = conn.cursor()
    stats = {"claims": 0, "mechanisms": 0, "findings": 0, "total": 0}

    paper_id = str(result.paper_id)
    paper_title = paper_meta.get("title", "Untitled")
    doi = paper_meta.get("doi", "")
    source_file = f"decoded/paper/{doi or paper_id}"
    journal = paper_meta.get("journal", "")
    year = ""
    if paper_meta.get("published_date"):
        year = str(paper_meta["published_date"])[:4]

    def _insert_entry(
        title: str,
        content: str,
        operation: str,
        entry_type: str,
        density: str = "body",
        confidence: str = "moderate",
        epistemic_tier: int = 1,
        structured_data: dict | None = None,
    ):
        entry_id = f"decoded-{uuid.uuid4().hex[:12]}"
        cur.execute(
            """
            INSERT INTO kb_entries (
                id, workstation, operation, entry_type,
                title, element, content,
                epistemic_tier, confidence, density,
                source_file, structured_data
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s
            )
            ON CONFLICT (id) DO NOTHING
            """,
            (
                entry_id,
                "decoded_connectome",
                operation,
                entry_type,
                title[:250],
                paper_title[:250],
                content,
                epistemic_tier,
                confidence,
                density,
                source_file,
                json.dumps(structured_data or {}),
            ),
        )
        return entry_id

    # --- Claims ---
    for claim in (result.claims or []):
        claim_type = getattr(claim, "claim_type", "descriptive") or "descriptive"
        operation = _CLAIM_OP_MAP.get(claim_type.lower(), "Synthesis")
        evidence = getattr(claim, "evidence_strength", None) or "moderate"
        density = _DENSITY_MAP.get(evidence.lower(), "body")

        title = _truncate(getattr(claim, "text", ""), 200) or "Claim"
        content = _build_claim_content(claim, paper_title, journal, year, doi)

        _insert_entry(
            title=title,
            content=content,
            operation=operation,
            entry_type="decoded_claim",
            density=density,
            confidence=evidence,
            structured_data={
                "paper_id": paper_id,
                "doi": doi,
                "claim_type": claim_type,
                "subject": getattr(claim, "subject", None),
                "predicate": getattr(claim, "predicate", None),
                "object": getattr(claim, "object", None),
                "section": getattr(claim, "section", None),
            },
        )
        stats["claims"] += 1

    # --- Mechanisms ---
    for mech in (result.mechanisms or []):
        desc = getattr(mech, "description", "") or ""
        if not desc:
            continue

        title = _truncate(desc, 200)
        content = _build_mech_content(mech, paper_title, journal, year, doi)
        density = _DENSITY_MAP.get(
            str(getattr(mech, "confidence", 0.7)),
            "mind"
        )
        # Use numeric confidence to set density
        conf_val = getattr(mech, "confidence", 0.7) or 0.7
        if conf_val >= 0.8:
            density = "spirit"
        elif conf_val >= 0.5:
            density = "mind"
        else:
            density = "body"

        _insert_entry(
            title=title,
            content=content,
            operation="Transduction",
            entry_type="decoded_mechanism",
            density=density,
            confidence="moderate",
            structured_data={
                "paper_id": paper_id,
                "doi": doi,
                "pathway": getattr(mech, "pathway", None),
                "upstream": getattr(mech, "upstream_entity", None),
                "downstream": getattr(mech, "downstream_entity", None),
                "interaction": getattr(mech, "interaction_type", None),
                "context": getattr(mech, "context", None),
            },
        )
        stats["mechanisms"] += 1

    # --- Key findings ---
    for finding in (result.key_findings or []):
        if not finding:
            continue
        _insert_entry(
            title=_truncate(finding, 200),
            content=f"Key finding from: {paper_title} ({year})\nJournal: {journal}\n\n{finding}",
            operation="Synthesis",
            entry_type="decoded_finding",
            density="mind",
            confidence="moderate",
            structured_data={"paper_id": paper_id, "doi": doi},
        )
        stats["findings"] += 1

    stats["total"] = stats["claims"] + stats["mechanisms"] + stats["findings"]

    if own_conn:
        conn.commit()
        conn.close()

    logger.info(
        "Pearl bridge: paper %s → %d entries (claims=%d, mechs=%d, findings=%d)",
        paper_id[:8],
        stats["total"],
        stats["claims"],
        stats["mechanisms"],
        stats["findings"],
    )
    return stats


def _truncate(text: str, max_len: int) -> str:
    if len(text) <= max_len:
        return text
    return text[:max_len - 3] + "..."


def _build_claim_content(claim, paper_title: str, journal: str, year: str, doi: str) -> str:
    parts = [f"Source: {paper_title}"]
    if journal:
        parts.append(f"Journal: {journal} ({year})")
    if doi:
        parts.append(f"DOI: {doi}")
    parts.append("")
    parts.append(f"Claim: {getattr(claim, 'text', '')}")

    subj = getattr(claim, "subject", None)
    pred = getattr(claim, "predicate", None)
    obj = getattr(claim, "object", None)
    if subj and pred and obj:
        parts.append(f"Structure: {subj} → {pred} → {obj}")

    evidence = getattr(claim, "evidence_strength", None)
    if evidence:
        parts.append(f"Evidence strength: {evidence}")

    section = getattr(claim, "section", None)
    if section:
        parts.append(f"From section: {section}")

    return "\n".join(parts)


def _build_mech_content(mech, paper_title: str, journal: str, year: str, doi: str) -> str:
    parts = [f"Source: {paper_title}"]
    if journal:
        parts.append(f"Journal: {journal} ({year})")
    if doi:
        parts.append(f"DOI: {doi}")
    parts.append("")
    parts.append(f"Mechanism: {getattr(mech, 'description', '')}")

    upstream = getattr(mech, "upstream_entity", None)
    interaction = getattr(mech, "interaction_type", None)
    downstream = getattr(mech, "downstream_entity", None)
    if upstream and downstream:
        arrow = f" {interaction} " if interaction else " → "
        parts.append(f"Pathway: {upstream}{arrow}{downstream}")

    pathway = getattr(mech, "pathway", None)
    if pathway:
        parts.append(f"Pathway context: {pathway}")

    context = getattr(mech, "context", None)
    if context:
        parts.append(f"Biological context: {context}")

    return "\n".join(parts)
