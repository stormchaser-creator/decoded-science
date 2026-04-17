"""GraphWorker: batch-build Neo4j graph from ingested + extracted papers.

CLI usage:
    python -m decoded.graph.worker
    python -m decoded.graph.worker --limit 50
    python -m decoded.graph.worker --paper-id <uuid>
    python -m decoded.graph.worker --connections   # also sync connection edges
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=False)

from decoded.graph.builder import GraphBuilder, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("decoded.graph.worker")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def get_db_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    psycopg2.extras.register_uuid(conn)
    return conn


def fetch_papers(conn, limit: int, paper_id: str | None = None) -> list[dict]:
    """Fetch all papers (with optional extraction join)."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if paper_id:
        cur.execute(
            """
            SELECT p.id, p.title, p.doi, p.journal, p.source, p.authors,
                   p.published_date, p.abstract, p.status, p.references_list,
                   e.entities, e.claims, e.mechanisms, e.methods, e.key_findings
            FROM raw_papers p
            LEFT JOIN extraction_results e ON e.paper_id = p.id
            WHERE p.id = %s
            """,
            (paper_id,),
        )
    else:
        cur.execute(
            """
            SELECT p.id, p.title, p.doi, p.journal, p.source, p.authors,
                   p.published_date, p.abstract, p.status, p.references_list,
                   e.entities, e.claims, e.mechanisms, e.methods, e.key_findings
            FROM raw_papers p
            LEFT JOIN extraction_results e ON e.paper_id = p.id
            WHERE p.title IS NOT NULL
            ORDER BY p.created_at DESC
            LIMIT %s
            """,
            (limit,),
        )
    return [dict(r) for r in cur.fetchall()]


def fetch_connections(conn, limit: int = 10_000) -> list[dict]:
    """Fetch discovered connections for graph edge creation (capped to prevent OOM)."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT id, paper_a_id, paper_b_id, connection_type, description, confidence
        FROM discovered_connections
        ORDER BY confidence DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# GraphWorker
# ---------------------------------------------------------------------------


class GraphWorker:
    """Batch graph builder — reads from Postgres, writes to Neo4j."""

    def __init__(
        self,
        neo4j_uri: str = NEO4J_URI,
        neo4j_user: str = NEO4J_USER,
        neo4j_password: str = NEO4J_PASSWORD,
        limit: int = 200,
        paper_id: str | None = None,
        sync_connections: bool = True,
    ):
        self.limit = limit
        self.paper_id = paper_id
        self.sync_connections = sync_connections
        self.builder = GraphBuilder(
            uri=neo4j_uri,
            user=neo4j_user,
            password=neo4j_password,
        )

    def run(self) -> dict:
        """Build the graph. Returns stats."""
        conn = get_db_conn()
        stats = {
            "papers_processed": 0,
            "papers_with_extraction": 0,
            "entities_added": 0,
            "claims_added": 0,
            "mechanisms_added": 0,
            "methods_added": 0,
            "citations_added": 0,
            "connections_added": 0,
            "errors": 0,
        }

        logger.info("Ensuring Neo4j constraints/indexes...")
        self.builder.ensure_constraints()

        papers = fetch_papers(conn, limit=self.limit, paper_id=self.paper_id)
        logger.info("Processing %d papers into Neo4j...", len(papers))

        for paper in papers:
            try:
                pid = str(paper["id"])

                # Always upsert the paper node
                self.builder.upsert_paper(paper)
                stats["papers_processed"] += 1

                # If we have extraction data, add entity/claim/etc nodes
                has_extraction = paper.get("entities") is not None
                if has_extraction:
                    extraction = {
                        "entities": paper.get("entities"),
                        "claims": paper.get("claims"),
                        "mechanisms": paper.get("mechanisms"),
                        "methods": paper.get("methods"),
                    }
                    counts = self.builder.upsert_extraction(pid, extraction)
                    stats["entities_added"] += counts["entities"]
                    stats["claims_added"] += counts["claims"]
                    stats["mechanisms_added"] += counts["mechanisms"]
                    stats["methods_added"] += counts["methods"]
                    stats["papers_with_extraction"] += 1

                # Citation edges from references_list
                refs_raw = paper.get("references_list")
                refs = []
                if isinstance(refs_raw, list):
                    refs = refs_raw
                elif isinstance(refs_raw, str):
                    try:
                        refs = json.loads(refs_raw)
                    except Exception:
                        refs = []
                if refs:
                    added = self.builder.add_citations(pid, refs)
                    stats["citations_added"] += added

                if stats["papers_processed"] % 10 == 0:
                    logger.info(
                        "Progress: %d/%d papers", stats["papers_processed"], len(papers)
                    )

            except Exception as exc:
                logger.error("Error processing paper %s: %s", paper.get("id"), exc, exc_info=True)
                stats["errors"] += 1

        # Sync connection edges from discovered_connections table
        # Re-open a fresh DB connection — the original may have been dropped
        # after being idle for the duration of the Neo4j processing loop.
        if self.sync_connections:
            conn.close()
            conn = get_db_conn()
            connections = fetch_connections(conn)
            logger.info("Syncing %d connection edges...", len(connections))
            for conn_row in connections:
                try:
                    self.builder.add_connection(
                        paper_a_id=str(conn_row["paper_a_id"]),
                        paper_b_id=str(conn_row["paper_b_id"]),
                        connection_type=conn_row["connection_type"],
                        description=conn_row["description"],
                        confidence=float(conn_row["confidence"]),
                        connection_db_id=str(conn_row["id"]),
                    )
                    stats["connections_added"] += 1
                except Exception as exc:
                    logger.error("Error adding connection edge: %s", exc)

        self.builder.close()
        conn.close()
        return stats

    def verify(self) -> dict:
        """Run verification queries and return counts."""
        nodes = self.builder.count_nodes()
        edges = self.builder.count_edges()
        return {"nodes": nodes, "edges": edges}


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Decoded graph worker — build Neo4j graph from paper data"
    )
    parser.add_argument("--limit", type=int, default=200,
                        help="Max papers to process (default: 200)")
    parser.add_argument("--paper-id", default=None,
                        help="Process a specific paper by UUID")
    parser.add_argument("--no-connections", action="store_true",
                        help="Skip syncing connection edges")
    parser.add_argument("--verify-only", action="store_true",
                        help="Only run verification queries, skip building")
    parser.add_argument("--neo4j-uri", default=NEO4J_URI)
    parser.add_argument("--neo4j-user", default=NEO4J_USER)
    parser.add_argument("--neo4j-password", default=NEO4J_PASSWORD)
    args = parser.parse_args()

    worker = GraphWorker(
        neo4j_uri=args.neo4j_uri,
        neo4j_user=args.neo4j_user,
        neo4j_password=args.neo4j_password,
        limit=args.limit,
        paper_id=args.paper_id,
        sync_connections=not args.no_connections,
    )

    if args.verify_only:
        # Just open a builder for verification
        builder = GraphBuilder(
            uri=args.neo4j_uri,
            user=args.neo4j_user,
            password=args.neo4j_password,
        )
        nodes = builder.count_nodes()
        edges = builder.count_edges()
        builder.close()
        print("\n=== Neo4j Graph State ===")
        print("Nodes:")
        for label, count in nodes.items():
            print(f"  {label}: {count:,}")
        print("Edges:")
        for rel, count in edges.items():
            print(f"  {rel}: {count:,}")
        total_nodes = sum(nodes.values())
        total_edges = sum(edges.values())
        print(f"\nTotal: {total_nodes:,} nodes, {total_edges:,} edges")
        return

    stats = worker.run()

    print("\n=== Graph Build Summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v:,}")

    # Exponential backoff when no new work to prevent tight restart loops
    if stats.get("papers_processed", 0) == 0:
        import time
        backoff = int(os.environ.get("DECODE_GRAPH_BACKOFF", "300"))
        logger.info("No new papers to graph — sleeping %ds before exit", backoff)
        time.sleep(backoff)

    # Final verification
    builder = GraphBuilder(
        uri=args.neo4j_uri,
        user=args.neo4j_user,
        password=args.neo4j_password,
    )
    nodes = builder.count_nodes()
    edges = builder.count_edges()
    builder.close()

    print("\n=== Neo4j Graph State ===")
    print("Nodes:")
    for label, count in nodes.items():
        print(f"  {label}: {count:,}")
    print("Edges:")
    for rel, count in edges.items():
        print(f"  {rel}: {count:,}")
    total_nodes = sum(nodes.values())
    total_edges = sum(edges.values())
    print(f"\nTotal: {total_nodes:,} nodes, {total_edges:,} edges")


if __name__ == "__main__":
    main()
