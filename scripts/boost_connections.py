"""Boost connection density via entity co-occurrence.

Creates new connections between papers sharing 3+ entities across different
subdisciplines (or 5+ entities within the same source).

Also cleans up 'replicates' connections from both Postgres and Neo4j.

Usage:
    python scripts/boost_connections.py --dry-run
    python scripts/boost_connections.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path
from uuid import uuid4

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env", override=True)

import psycopg2
import psycopg2.extras

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("boost_connections")

DB_URL = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")


def get_conn():
    c = psycopg2.connect(DB_URL)
    psycopg2.extras.register_uuid(c)
    return c


def normalize_entity(e) -> str | None:
    """Extract canonical text from an entity object."""
    if isinstance(e, str):
        return e.strip().lower() if e.strip() else None
    if isinstance(e, dict):
        text = e.get("text") or e.get("name") or e.get("value") or ""
        return text.strip().lower() if text.strip() else None
    return None


def get_paper_entities(conn) -> dict[str, set[str]]:
    """Return {paper_id: {entity_name, ...}} for all extracted papers."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT er.paper_id, er.entities, p.source
        FROM extraction_results er
        JOIN raw_papers p ON p.id = er.paper_id
        WHERE er.entities IS NOT NULL
          AND er.entities != 'null'
          AND er.entities::text LIKE '[%'
        """
    )
    result = {}
    sources = {}
    for row in cur.fetchall():
        pid = str(row["paper_id"])
        sources[pid] = row["source"] or "unknown"
        entities_raw = row["entities"]
        if isinstance(entities_raw, str):
            try:
                entities_raw = json.loads(entities_raw)
            except Exception:
                continue
        if not isinstance(entities_raw, list):
            continue
        normalized = set()
        for e in entities_raw:
            n = normalize_entity(e)
            if n and len(n) > 2:
                normalized.add(n)
        if normalized:
            result[pid] = normalized
    return result, sources


def get_existing_pairs(conn) -> set[tuple[str, str]]:
    """Return set of (a, b) pairs that already have connections (canonical order)."""
    cur = conn.cursor()
    cur.execute("SELECT paper_a_id, paper_b_id FROM discovered_connections")
    pairs = set()
    for row in cur.fetchall():
        a, b = str(row[0]), str(row[1])
        pairs.add((min(a, b), max(a, b)))
    return pairs


def delete_replicates(conn, dry_run: bool) -> int:
    """Delete all replicates connections from Postgres."""
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM discovered_connections WHERE connection_type = 'replicates'")
    n = cur.fetchone()[0]
    logger.info("Found %d replicates connections to delete", n)
    if not dry_run and n > 0:
        cur.execute("DELETE FROM discovered_connections WHERE connection_type = 'replicates'")
        conn.commit()
        logger.info("Deleted %d replicates connections from Postgres", n)
    return n


def delete_neo4j_replicates(dry_run: bool) -> int:
    """Delete replicates relationships from Neo4j."""
    try:
        from neo4j import GraphDatabase
        uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        user = os.environ.get("NEO4J_USER", "neo4j")
        pw = os.environ.get("NEO4J_PASSWORD", "decoded123")
        driver = GraphDatabase.driver(uri, auth=(user, pw))
        with driver.session() as s:
            count_result = s.run(
                "MATCH ()-[r:CONNECTED_TO {connection_type: 'replicates'}]->() RETURN count(r) as n"
            ).single()
            n = count_result["n"] if count_result else 0
            logger.info("Found %d Neo4j replicates edges to delete", n)
            if not dry_run and n > 0:
                s.run(
                    "MATCH ()-[r:CONNECTED_TO {connection_type: 'replicates'}]->() DELETE r"
                )
        driver.close()
        return n
    except Exception as exc:
        logger.warning("Neo4j replicates cleanup failed (Neo4j may not be running): %s", exc)
        return 0


def insert_connections(conn, new_connections: list[dict], dry_run: bool) -> int:
    """Insert new entity-co-occurrence connections."""
    if not new_connections:
        return 0
    if dry_run:
        logger.info("[dry-run] Would insert %d new connections", len(new_connections))
        return len(new_connections)
    inserted = 0
    for c in new_connections:
        try:
            cur = conn.cursor()
            cur.execute(
                """
                INSERT INTO discovered_connections
                    (id, paper_a_id, paper_b_id, connection_type, description,
                     confidence, novelty_score, model_id, cost_usd, created_at)
                VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, %s, %s, 'entity-cooccurrence', 0, NOW())
                ON CONFLICT DO NOTHING
                """,
                (
                    str(uuid4()),
                    c["paper_a_id"],
                    c["paper_b_id"],
                    c["connection_type"],
                    c["description"],
                    c["confidence"],
                    c["novelty_score"],
                ),
            )
            conn.commit()
            inserted += 1
        except Exception as exc:
            conn.rollback()
            logger.debug("Insert failed: %s", exc)
    return inserted


def build_co_occurrence_connections(
    paper_entities: dict,
    paper_sources: dict,
    existing_pairs: set,
    cross_threshold: int = 3,
    same_threshold: int = 5,
    max_new: int = 5000,
) -> list[dict]:
    """Find papers sharing enough entities to create new connections."""
    pids = list(paper_entities.keys())
    logger.info("Building co-occurrence index for %d papers...", len(pids))

    # Build inverted index: entity -> [paper_ids]
    entity_index: dict[str, list[str]] = {}
    for pid, entities in paper_entities.items():
        for e in entities:
            if e not in entity_index:
                entity_index[e] = []
            entity_index[e].append(pid)

    # Count shared entities between pairs
    logger.info("Counting shared entities between pairs...")
    pair_counts: dict[tuple[str, str], int] = {}
    for entity, papers in entity_index.items():
        if len(papers) < 2 or len(papers) > 500:  # skip very common entities
            continue
        for i in range(len(papers)):
            for j in range(i + 1, len(papers)):
                a, b = papers[i], papers[j]
                key = (min(a, b), max(a, b))
                pair_counts[key] = pair_counts.get(key, 0) + 1

    logger.info("Found %d unique paper pairs with shared entities", len(pair_counts))

    new_connections = []
    for (a, b), count in sorted(pair_counts.items(), key=lambda x: -x[1]):
        if len(new_connections) >= max_new:
            break
        # Skip existing pairs
        if (a, b) in existing_pairs or (b, a) in existing_pairs:
            continue

        src_a = paper_sources.get(a, "unknown")
        src_b = paper_sources.get(b, "unknown")
        cross_discipline = src_a != src_b

        threshold = cross_threshold if cross_discipline else same_threshold
        if count < threshold:
            continue

        shared = paper_entities[a] & paper_entities[b]
        top_entities = sorted(shared)[:5]
        description = (
            f"Entity co-occurrence: {count} shared concepts including "
            + ", ".join(top_entities[:3])
            + ("..." if len(top_entities) > 3 else ".")
        )
        confidence = min(0.95, 0.5 + count * 0.05)
        novelty = 0.3 if cross_discipline else 0.1

        new_connections.append({
            "paper_a_id": a,
            "paper_b_id": b,
            "connection_type": "convergent_evidence",
            "description": description,
            "confidence": round(confidence, 3),
            "novelty_score": round(novelty, 3),
        })

    return new_connections


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--dry-run", action="store_true", help="Don't write to DB")
    parser.add_argument("--cross-threshold", type=int, default=3, help="Min shared entities cross-discipline (default: 3)")
    parser.add_argument("--same-threshold", type=int, default=5, help="Min shared entities same-discipline (default: 5)")
    parser.add_argument("--max-new", type=int, default=5000, help="Max new connections to create (default: 5000)")
    parser.add_argument("--skip-cleanup", action="store_true", help="Skip replicates cleanup")
    args = parser.parse_args()

    conn = get_conn()

    # Step 1: Delete replicates
    if not args.skip_cleanup:
        n_pg = delete_replicates(conn, args.dry_run)
        n_neo = delete_neo4j_replicates(args.dry_run)
        logger.info("Replicates cleanup: %d Postgres, %d Neo4j", n_pg, n_neo)

    # Step 2: Load entity data
    logger.info("Loading paper entities...")
    paper_entities, paper_sources = get_paper_entities(conn)
    logger.info("Loaded entities for %d papers", len(paper_entities))

    # Step 3: Load existing pairs
    existing_pairs = get_existing_pairs(conn)
    logger.info("Existing connection pairs: %d", len(existing_pairs))

    # Step 4: Build co-occurrence connections
    new_conns = build_co_occurrence_connections(
        paper_entities,
        paper_sources,
        existing_pairs,
        cross_threshold=args.cross_threshold,
        same_threshold=args.same_threshold,
        max_new=args.max_new,
    )
    logger.info("Found %d candidate new connections", len(new_conns))

    # Step 5: Insert
    inserted = insert_connections(conn, new_conns, args.dry_run)
    logger.info("Inserted %d new connections", inserted)

    # Final count
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM discovered_connections WHERE connection_type != 'replicates'")
    total = cur.fetchone()[0]
    logger.info("Total connections in DB (excl replicates): %d", total)

    conn.close()


if __name__ == "__main__":
    main()
