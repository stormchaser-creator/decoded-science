"""Batch bridge — query raw_papers by author/topic and bridge to Pearl's kb_entries.

This is the missing piece: a CLI that selects papers from Decoded's raw_papers,
joins extraction_results where available, and pushes everything into Pearl's
kb_entries via the existing bridge_extraction_to_pearl() function.

Papers WITH extractions → claims/mechanisms/findings → kb_entries (structured)
Papers WITHOUT extractions → title+abstract → kb_entries (raw academic entry)

Usage:
    # Bridge all Altini papers (extracted + raw)
    python -m decoded.pearl.batch_bridge --author "Altini" --dry-run
    python -m decoded.pearl.batch_bridge --author "Altini"

    # Bridge by topic
    python -m decoded.pearl.batch_bridge --topic "heart rate variability" --limit 50

    # Bridge specific paper by DOI
    python -m decoded.pearl.batch_bridge --doi "10.1016/j.bspc.2021.103273"

    # Bridge all extracted papers not yet bridged
    python -m decoded.pearl.batch_bridge --unbridged --limit 100
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import psycopg2
import psycopg2.extras

from decoded.pearl.bridge import bridge_extraction_to_pearl, DECODED_SOURCE_AUTHORITY

logger = logging.getLogger("decoded.pearl.batch_bridge")

# ---------------------------------------------------------------------------
# Models (lightweight — avoid importing full Pydantic stack for CLI)
# ---------------------------------------------------------------------------


@dataclass
class PaperRow:
    """Minimal paper data from raw_papers."""
    id: str
    source: str
    external_id: str
    title: str
    abstract: str | None
    authors: list[str]
    journal: str | None
    published_date: Any  # date or None
    doi: str | None
    pmc_id: str | None
    mesh_terms: list[str]
    keywords: list[str]
    status: str
    full_text: str | None = None


@dataclass
class ExtractionRow:
    """Extraction result joined to a paper."""
    paper_id: str
    model_id: str
    study_design: str
    claims: list[dict]
    mechanisms: list[dict]
    key_findings: list[str]
    methods: list[dict]
    entities: list[dict]
    limitations: list[str]


@dataclass
class BridgeStats:
    """Aggregate stats for a batch run."""
    papers_found: int = 0
    papers_with_extractions: int = 0
    papers_raw_only: int = 0
    entries_created: int = 0
    claims_bridged: int = 0
    mechanisms_bridged: int = 0
    findings_bridged: int = 0
    raw_entries_created: int = 0
    connections_bridged: int = 0
    signals_emitted: int = 0
    skipped_no_abstract: int = 0
    errors: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Asymmetric connection thresholds (Pearl + Claude review 2026-04-08)
# ---------------------------------------------------------------------------

# High-priority: top-quality novel connections → KB
THRESHOLD_HIGH_PRIORITY = {"confidence": 0.80, "novelty": 0.50}
# Standard: confirmatory connections welcome (grounds existing work)
THRESHOLD_STANDARD = {"confidence": 0.70, "novelty": 0.30}
# Signal trigger: only these fire pearl_signals
THRESHOLD_SIGNAL = {"confidence": 0.70, "novelty": 0.75}
# Immediate bridge: skip nightly cron for very high confidence
THRESHOLD_IMMEDIATE = {"confidence": 0.90}


# ---------------------------------------------------------------------------
# Extraction result adapter — convert DB rows to objects bridge.py expects
# ---------------------------------------------------------------------------


class _ClaimProxy:
    """Minimal object that bridge_extraction_to_pearl can getattr() on."""
    def __init__(self, d: dict):
        self.text = d.get("text", "")
        self.claim_type = d.get("claim_type", "descriptive")
        self.subject = d.get("subject")
        self.predicate = d.get("predicate")
        self.object = d.get("object")
        self.evidence_strength = d.get("evidence_strength", "moderate")
        self.confidence = d.get("confidence", 0.7)
        self.section = d.get("section")


class _MechProxy:
    """Minimal object for mechanism data."""
    def __init__(self, d: dict):
        self.description = d.get("description", "")
        self.pathway = d.get("pathway")
        self.upstream_entity = d.get("upstream_entity")
        self.downstream_entity = d.get("downstream_entity")
        self.interaction_type = d.get("interaction_type")
        self.context = d.get("context")
        self.confidence = d.get("confidence", 0.7)


class _ExtractionProxy:
    """Wraps DB row to look like an ExtractionResult for bridge.py."""
    def __init__(self, row: ExtractionRow):
        self.paper_id = row.paper_id
        self.claims = [_ClaimProxy(c) for c in (row.claims or [])]
        self.mechanisms = [_MechProxy(m) for m in (row.mechanisms or [])]
        self.key_findings = row.key_findings or []


# ---------------------------------------------------------------------------
# Database queries
# ---------------------------------------------------------------------------


def _get_conn():
    db_url = os.environ.get(
        "DATABASE_URL",
        "postgresql://whit@localhost:5432/encoded_human",
    )
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    psycopg2.extras.register_uuid(conn)
    return conn


def _fetch_papers(
    conn,
    *,
    author: str | None = None,
    topic: str | None = None,
    doi: str | None = None,
    unbridged: bool = False,
    limit: int = 100,
) -> list[PaperRow]:
    """Query raw_papers with filters."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    conditions = []
    params: list[Any] = []

    if author:
        # Search authors JSONB array for matching name
        conditions.append("authors::text ILIKE %s")
        params.append(f"%{author}%")

    if topic:
        conditions.append("(title ILIKE %s OR abstract ILIKE %s)")
        params.extend([f"%{topic}%", f"%{topic}%"])

    if doi:
        conditions.append("doi = %s")
        params.append(doi)

    if unbridged:
        # Only papers with extractions that haven't been bridged yet
        conditions.append("""
            EXISTS (SELECT 1 FROM extraction_results er WHERE er.paper_id = raw_papers.id)
            AND NOT EXISTS (
                SELECT 1 FROM kb_entries ke
                WHERE ke.workstation = 'decoded_connectome'
                  AND ke.structured_data->>'paper_id' = raw_papers.id::text
            )
        """)

    where = " AND ".join(conditions) if conditions else "TRUE"

    query = f"""
        SELECT id, source, external_id, title, abstract, authors,
               journal, published_date, doi, pmc_id, mesh_terms,
               keywords, status, full_text
        FROM raw_papers
        WHERE {where}
        ORDER BY published_date DESC NULLS LAST
        LIMIT %s
    """
    params.append(limit)

    cur.execute(query, params)
    rows = cur.fetchall()

    papers = []
    for r in rows:
        papers.append(PaperRow(
            id=str(r["id"]),
            source=r["source"],
            external_id=r["external_id"],
            title=r["title"],
            abstract=r.get("abstract"),
            authors=r.get("authors") or [],
            journal=r.get("journal"),
            published_date=r.get("published_date"),
            doi=r.get("doi"),
            pmc_id=r.get("pmc_id"),
            mesh_terms=r.get("mesh_terms") or [],
            keywords=r.get("keywords") or [],
            status=r["status"],
            full_text=r.get("full_text"),
        ))

    return papers


def _fetch_extraction(conn, paper_id: str) -> ExtractionRow | None:
    """Get extraction results for a paper, if they exist."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT paper_id, model_id, study_design,
               claims, mechanisms, key_findings, methods,
               entities, limitations
        FROM extraction_results
        WHERE paper_id = %s
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (paper_id,),
    )
    row = cur.fetchone()
    if not row:
        return None

    return ExtractionRow(
        paper_id=str(row["paper_id"]),
        model_id=row["model_id"],
        study_design=row.get("study_design", "unknown"),
        claims=row.get("claims") or [],
        mechanisms=row.get("mechanisms") or [],
        key_findings=row.get("key_findings") or [],
        methods=row.get("methods") or [],
        entities=row.get("entities") or [],
        limitations=row.get("limitations") or [],
    )


# ---------------------------------------------------------------------------
# Raw paper → kb_entry (no extraction available)
# ---------------------------------------------------------------------------


def _bridge_raw_paper(conn, paper: PaperRow, dry_run: bool = False) -> int:
    """Bridge a raw paper (title + abstract) directly to kb_entries.

    Used when no extraction_results exist. Creates a single kb_entry
    with the abstract as content, tagged as 'decoded_raw_paper'.
    """
    if not paper.abstract or len(paper.abstract.strip()) < 50:
        return 0

    entry_id = f"decoded-raw-{uuid.uuid4().hex[:12]}"
    year = str(paper.published_date)[:4] if paper.published_date else ""
    authors_str = ", ".join(paper.authors[:5]) if isinstance(paper.authors, list) else ""

    content_parts = [f"Source: {paper.title}"]
    if paper.journal:
        content_parts.append(f"Journal: {paper.journal} ({year})")
    if paper.doi:
        content_parts.append(f"DOI: {paper.doi}")
    if authors_str:
        content_parts.append(f"Authors: {authors_str}")
    content_parts.append("")
    content_parts.append(paper.abstract)

    if paper.mesh_terms:
        terms = paper.mesh_terms[:10] if isinstance(paper.mesh_terms, list) else []
        if terms:
            content_parts.append("")
            content_parts.append(f"MeSH Terms: {'; '.join(str(t) for t in terms)}")

    content = "\n".join(content_parts)

    if dry_run:
        return 1

    cur = conn.cursor()
    cur.execute(
        """
        INSERT INTO kb_entries (
            id, workstation, operation, entry_type,
            title, element, content,
            epistemic_tier, confidence, density,
            source_file, structured_data, source_authority
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s
        )
        ON CONFLICT (id) DO NOTHING
        """,
        (
            entry_id,
            "decoded_connectome",
            "Reception",  # raw paper = pattern detection
            "decoded_raw_paper",
            paper.title[:250],
            paper.title[:250],
            content,
            1,  # epistemic tier 1 = peer-reviewed science
            "moderate",
            "soul",  # raw paper = pattern-level (moderate evidence, unclassified)
            f"decoded/paper/{paper.doi or paper.id}",
            json.dumps({
                "paper_id": paper.id,
                "doi": paper.doi,
                "pmid": paper.external_id if paper.source == "pubmed" else None,
                "pmc_id": paper.pmc_id,
                "journal": paper.journal,
                "authors": paper.authors[:5] if isinstance(paper.authors, list) else [],
                "mesh_terms": paper.mesh_terms[:10] if isinstance(paper.mesh_terms, list) else [],
                "keywords": paper.keywords[:10] if isinstance(paper.keywords, list) else [],
                "published_date": str(paper.published_date) if paper.published_date else None,
                "source": paper.source,
                "bridge_type": "raw",  # distinguishes from extracted entries
            }),
            DECODED_SOURCE_AUTHORITY,
        ),
    )
    return 1


# ---------------------------------------------------------------------------
# Connection bridging — discovered_connections → kb_entries + pearl_signals
# ---------------------------------------------------------------------------


def _fetch_unbridged_connections(
    conn,
    *,
    limit: int = 200,
) -> list[dict]:
    """Fetch discovered_connections that pass asymmetric thresholds and aren't bridged yet."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT dc.id, dc.paper_a_id, dc.paper_b_id, dc.connection_type,
               dc.description, dc.confidence, dc.novelty_score,
               dc.supporting_evidence, dc.created_at,
               pa.title AS paper_a_title, pa.doi AS paper_a_doi,
               pb.title AS paper_b_title, pb.doi AS paper_b_doi
        FROM discovered_connections dc
        JOIN raw_papers pa ON pa.id = dc.paper_a_id
        JOIN raw_papers pb ON pb.id = dc.paper_b_id
        WHERE dc.confidence >= %(min_confidence)s
          AND COALESCE(dc.novelty_score, 0) >= %(min_novelty)s
          AND NOT EXISTS (
              SELECT 1 FROM kb_entries ke
              WHERE ke.workstation = 'decoded_connectome'
                AND ke.entry_type = 'decoded_connection'
                AND ke.structured_data->>'connection_id' = dc.id::text
          )
        ORDER BY dc.confidence DESC, dc.novelty_score DESC
        LIMIT %(limit)s
        """,
        {
            "min_confidence": THRESHOLD_STANDARD["confidence"],
            "min_novelty": THRESHOLD_STANDARD["novelty"],
            "limit": limit,
        },
    )
    return cur.fetchall()


def _count_related_kb_entries(conn, paper_a_doi: str | None, paper_b_doi: str | None) -> int:
    """Count how many existing Pearl KB entries reference either paper."""
    if not paper_a_doi and not paper_b_doi:
        return 0
    cur = conn.cursor()
    dois = [d for d in [paper_a_doi, paper_b_doi] if d]
    placeholders = " OR ".join(
        f"content ILIKE '%' || %s || '%'" for _ in dois
    )
    cur.execute(
        f"SELECT COUNT(*) FROM kb_entries WHERE {placeholders}",
        dois,
    )
    return cur.fetchone()[0]


def _bridge_connection(conn, row: dict, dry_run: bool = False) -> tuple[bool, bool]:
    """Bridge a single discovered_connection to kb_entries.

    Returns (entry_created, signal_emitted).
    """
    confidence = float(row["confidence"] or 0)
    novelty = float(row["novelty_score"] or 0)

    # Determine density from confidence (inverted mapping)
    if confidence >= 0.8:
        density = "body"     # high confidence = most measurable
    elif confidence >= 0.5:
        density = "soul"     # moderate = pattern-level
    else:
        density = "spirit"   # low = field-level signal

    # Determine if this is high-priority
    is_high_priority = (
        confidence >= THRESHOLD_HIGH_PRIORITY["confidence"]
        and novelty >= THRESHOLD_HIGH_PRIORITY["novelty"]
    )

    entry_id = f"decoded-conn-{uuid.uuid4().hex[:12]}"
    connection_id = str(row["id"])

    content_parts = [
        f"Connection: {row['paper_a_title']} ←[{row['connection_type']}]→ {row['paper_b_title']}",
        f"",
        f"{row['description']}",
        f"",
        f"Confidence: {confidence:.2f}",
        f"Novelty: {novelty:.2f}",
        f"Type: {row['connection_type']}",
    ]
    if row.get("paper_a_doi"):
        content_parts.append(f"Paper A DOI: {row['paper_a_doi']}")
    if row.get("paper_b_doi"):
        content_parts.append(f"Paper B DOI: {row['paper_b_doi']}")

    if row.get("supporting_evidence"):
        try:
            evidence = json.loads(row["supporting_evidence"]) if isinstance(row["supporting_evidence"], str) else row["supporting_evidence"]
            if evidence:
                content_parts.append(f"Supporting evidence: {json.dumps(evidence, indent=2)}")
        except (json.JSONDecodeError, TypeError):
            pass

    content = "\n".join(content_parts)

    if not dry_run:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO kb_entries (
                id, workstation, operation, entry_type,
                title, element, content,
                epistemic_tier, confidence, density,
                source_file, structured_data, source_authority
            ) VALUES (
                %s, %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s,
                %s, %s, %s
            )
            ON CONFLICT (id) DO NOTHING
            """,
            (
                entry_id,
                "decoded_connectome",
                "Synthesis",                # connections are always Synthesis
                "decoded_connection",
                f"Connection: {row['paper_a_title'][:100]} ←→ {row['paper_b_title'][:100]}"[:250],
                f"{row['paper_a_title'][:120]} + {row['paper_b_title'][:120]}"[:250],
                content,
                2,                          # connections are Tier 2 (LLM-validated)
                f"{confidence:.2f}",
                density,
                f"decoded/connection/{connection_id}",
                json.dumps({
                    "connection_id": connection_id,
                    "paper_a_id": str(row["paper_a_id"]),
                    "paper_b_id": str(row["paper_b_id"]),
                    "paper_a_doi": row.get("paper_a_doi"),
                    "paper_b_doi": row.get("paper_b_doi"),
                    "connection_type": row["connection_type"],
                    "confidence": confidence,
                    "novelty": novelty,
                    "is_high_priority": is_high_priority,
                }),
                DECODED_SOURCE_AUTHORITY,
            ),
        )

    # Check if this should fire a pearl_signal
    signal_emitted = False
    should_signal = (
        confidence >= THRESHOLD_SIGNAL["confidence"]
        and novelty >= THRESHOLD_SIGNAL["novelty"]
    )

    if should_signal and not dry_run:
        # Count related KB entries for enriched payload
        related_count = _count_related_kb_entries(
            conn, row.get("paper_a_doi"), row.get("paper_b_doi")
        )

        # Count supporting evidence papers
        evidence_count = 0
        if row.get("supporting_evidence"):
            try:
                ev = json.loads(row["supporting_evidence"]) if isinstance(row["supporting_evidence"], str) else row["supporting_evidence"]
                evidence_count = len(ev) if isinstance(ev, list) else 0
            except (json.JSONDecodeError, TypeError):
                pass

        # Suggest operation based on connection type
        op_suggestion = _CLAIM_OP_MAP_FOR_CONNECTIONS.get(
            row.get("connection_type", ""), "Synthesis"
        )

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO pearl_signals (
                signal_type, priority, title, description, source, metadata
            ) VALUES (%s, %s, %s, %s, %s, %s)
            """,
            (
                "decoded_novel_connection",
                "high" if is_high_priority else "medium",
                f"Novel connection: {row['paper_a_title'][:60]} ↔ {row['paper_b_title'][:60]}"[:250],
                row["description"][:1000] if row.get("description") else "",
                "decoded-pearl-bridge",
                json.dumps({
                    "connection_id": connection_id,
                    "paper_a_doi": row.get("paper_a_doi"),
                    "paper_b_doi": row.get("paper_b_doi"),
                    "confidence": confidence,
                    "novelty": novelty,
                    "kb_entry_id": entry_id,
                    "evidence_count": evidence_count,
                    "related_kb_entry_count": related_count,
                    "suggested_operation": op_suggestion,
                }),
            ),
        )
        signal_emitted = True
        logger.info(
            "  [SIGNAL] Novel connection (conf=%.2f, nov=%.2f): %s ↔ %s",
            confidence, novelty,
            row["paper_a_title"][:40], row["paper_b_title"][:40],
        )

    return True, signal_emitted


# Connection type → suggested Pearl operation (for enriched signal payload)
_CLAIM_OP_MAP_FOR_CONNECTIONS = {
    "causal":       "Conduction",
    "mechanistic":  "Transduction",
    "associative":  "Reception",
    "convergent":   "Synthesis",
    "complementary": "Synthesis",
    "contradictory": "Synthesis",
}


def bridge_connection_immediately(connection_row: dict):
    """Immediate bridge for confidence ≥ 0.90 connections.

    Called from Decoded's extract/connect pipeline via on_extract hook.
    Bridges a single connection without waiting for the nightly cron.
    """
    confidence = float(connection_row.get("confidence", 0))
    if confidence < THRESHOLD_IMMEDIATE["confidence"]:
        return

    conn = _get_conn()
    try:
        entry_created, signal_emitted = _bridge_connection(conn, connection_row)
        conn.commit()
        logger.info(
            "Immediate bridge: connection %s (conf=%.2f) → entry=%s, signal=%s",
            connection_row.get("id", "?"),
            confidence,
            entry_created,
            signal_emitted,
        )
    except Exception as e:
        conn.rollback()
        logger.error("Immediate bridge failed for connection %s: %s", connection_row.get("id"), e)
    finally:
        conn.close()


# ---------------------------------------------------------------------------
# Main batch bridge
# ---------------------------------------------------------------------------


def run_batch_bridge(
    *,
    author: str | None = None,
    topic: str | None = None,
    doi: str | None = None,
    unbridged: bool = False,
    limit: int = 100,
    dry_run: bool = False,
) -> BridgeStats:
    """Run the batch bridge pipeline.

    1. Query raw_papers with filters
    2. For each paper, check for extraction_results
    3. If extracted → bridge_extraction_to_pearl() (claims/mechanisms/findings)
    4. If not extracted → bridge raw title+abstract as kb_entry
    5. Return stats
    """
    stats = BridgeStats()
    conn = _get_conn()

    try:
        # 1. Find matching papers
        papers = _fetch_papers(
            conn,
            author=author,
            topic=topic,
            doi=doi,
            unbridged=unbridged,
            limit=limit,
        )
        stats.papers_found = len(papers)
        logger.info("Found %d papers matching query", len(papers))

        if not papers:
            logger.info("No papers found. Skipping paper bridging — will still process connections.")

        # 2. Process each paper
        for paper in papers:
            try:
                extraction = _fetch_extraction(conn, paper.id)

                if extraction and (extraction.claims or extraction.mechanisms or extraction.key_findings):
                    # Has structured extraction → use full bridge
                    stats.papers_with_extractions += 1

                    if dry_run:
                        n_claims = len(extraction.claims)
                        n_mechs = len(extraction.mechanisms)
                        n_findings = len(extraction.key_findings)
                        stats.claims_bridged += n_claims
                        stats.mechanisms_bridged += n_mechs
                        stats.findings_bridged += n_findings
                        stats.entries_created += n_claims + n_mechs + n_findings
                        logger.info(
                            "  [DRY RUN] %s → %d claims, %d mechanisms, %d findings",
                            paper.title[:60],
                            n_claims, n_mechs, n_findings,
                        )
                    else:
                        proxy = _ExtractionProxy(extraction)
                        paper_meta = {
                            "title": paper.title,
                            "doi": paper.doi,
                            "journal": paper.journal,
                            "published_date": str(paper.published_date) if paper.published_date else "",
                            "authors": paper.authors[:5] if isinstance(paper.authors, list) else [],
                        }
                        result = bridge_extraction_to_pearl(proxy, paper_meta, conn=conn)
                        stats.claims_bridged += result["claims"]
                        stats.mechanisms_bridged += result["mechanisms"]
                        stats.findings_bridged += result["findings"]
                        stats.entries_created += result["total"]
                else:
                    # No extraction → bridge raw abstract
                    stats.papers_raw_only += 1

                    if not paper.abstract or len(paper.abstract.strip()) < 50:
                        stats.skipped_no_abstract += 1
                        logger.info(
                            "  [SKIP] %s — no abstract",
                            paper.title[:60],
                        )
                        continue

                    created = _bridge_raw_paper(conn, paper, dry_run=dry_run)
                    stats.raw_entries_created += created
                    stats.entries_created += created

                    if dry_run:
                        logger.info(
                            "  [DRY RUN] %s → 1 raw entry",
                            paper.title[:60],
                        )

            except Exception as e:
                msg = f"Error bridging paper {paper.id}: {e}"
                logger.error(msg)
                stats.errors.append(msg)

        # 3. Bridge discovered connections (asymmetric thresholds)
        logger.info("Bridging discovered connections...")
        connections = _fetch_unbridged_connections(conn, limit=limit)
        logger.info("Found %d unbridged connections above threshold", len(connections))

        for conn_row in connections:
            try:
                entry_created, signal_emitted = _bridge_connection(conn, conn_row, dry_run=dry_run)
                if entry_created:
                    stats.connections_bridged += 1
                    stats.entries_created += 1
                if signal_emitted:
                    stats.signals_emitted += 1

                if dry_run:
                    conf = float(conn_row.get("confidence", 0))
                    nov = float(conn_row.get("novelty_score", 0))
                    logger.info(
                        "  [DRY RUN] Connection (conf=%.2f, nov=%.2f): %s ↔ %s%s",
                        conf, nov,
                        conn_row["paper_a_title"][:40],
                        conn_row["paper_b_title"][:40],
                        " [SIGNAL]" if (conf >= THRESHOLD_SIGNAL["confidence"] and nov >= THRESHOLD_SIGNAL["novelty"]) else "",
                    )
            except Exception as e:
                msg = f"Error bridging connection {conn_row.get('id')}: {e}"
                logger.error(msg)
                stats.errors.append(msg)

        # 4. Commit
        if not dry_run:
            conn.commit()
            logger.info("Committed %d entries to kb_entries", stats.entries_created)
        else:
            conn.rollback()
            logger.info("[DRY RUN] Would create %d entries", stats.entries_created)

    except Exception as e:
        conn.rollback()
        logger.error("Batch bridge failed: %s", e)
        stats.errors.append(str(e))
        raise
    finally:
        conn.close()

    return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Bridge Decoded raw_papers → Pearl kb_entries",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Preview Altini papers (no DB writes)
  python -m decoded.pearl.batch_bridge --author "Altini" --dry-run

  # Bridge Altini papers for real
  python -m decoded.pearl.batch_bridge --author "Altini"

  # Bridge HRV papers by topic
  python -m decoded.pearl.batch_bridge --topic "heart rate variability" --limit 50

  # Bridge all extracted papers not yet in Pearl
  python -m decoded.pearl.batch_bridge --unbridged --limit 200
        """,
    )
    parser.add_argument("--author", help="Filter by author name (case-insensitive)")
    parser.add_argument("--topic", help="Filter by title/abstract keyword")
    parser.add_argument("--doi", help="Filter by exact DOI")
    parser.add_argument("--unbridged", action="store_true", help="Only papers with extractions not yet in kb_entries")
    parser.add_argument("--limit", type=int, default=100, help="Max papers to process (default: 100)")
    parser.add_argument("--dry-run", action="store_true", help="Preview what would be bridged (no DB writes)")
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose logging")

    args = parser.parse_args()

    if not any([args.author, args.topic, args.doi, args.unbridged]):
        parser.error("At least one filter required: --author, --topic, --doi, or --unbridged")

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
        datefmt="%H:%M:%S",
    )

    print(f"\n{'=' * 60}")
    print(f"  Decoded → Pearl Bridge")
    print(f"  {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    if args.dry_run:
        print(f"  MODE: DRY RUN (no writes)")
    print(f"{'=' * 60}\n")

    if args.author:
        print(f"  Author filter: {args.author}")
    if args.topic:
        print(f"  Topic filter:  {args.topic}")
    if args.doi:
        print(f"  DOI filter:    {args.doi}")
    if args.unbridged:
        print(f"  Unbridged only: yes")
    print(f"  Limit:         {args.limit}")
    print()

    stats = run_batch_bridge(
        author=args.author,
        topic=args.topic,
        doi=args.doi,
        unbridged=args.unbridged,
        limit=args.limit,
        dry_run=args.dry_run,
    )

    # Report
    print(f"\n{'=' * 60}")
    print(f"  Results")
    print(f"{'=' * 60}")
    print(f"  Papers found:              {stats.papers_found}")
    print(f"  With extractions:          {stats.papers_with_extractions}")
    print(f"  Raw only (no extraction):  {stats.papers_raw_only}")
    print(f"  Skipped (no abstract):     {stats.skipped_no_abstract}")
    print(f"  ---")
    print(f"  Claims bridged:            {stats.claims_bridged}")
    print(f"  Mechanisms bridged:        {stats.mechanisms_bridged}")
    print(f"  Findings bridged:          {stats.findings_bridged}")
    print(f"  Raw entries created:       {stats.raw_entries_created}")
    print(f"  Connections bridged:       {stats.connections_bridged}")
    print(f"  Signals emitted:           {stats.signals_emitted}")
    print(f"  ---")
    print(f"  TOTAL entries:             {stats.entries_created}")

    if stats.errors:
        print(f"\n  Errors ({len(stats.errors)}):")
        for err in stats.errors[:10]:
            print(f"    - {err}")

    print()

    return 0 if not stats.errors else 1


if __name__ == "__main__":
    sys.exit(main())
