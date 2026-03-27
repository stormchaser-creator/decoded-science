"""Connection discovery worker — three-phase orchestration.

Phase 1: Graph discovery (Neo4j shared nodes)
Phase 2: Embedding similarity (pgvector)
Phase 3: LLM validation (Claude Sonnet)

Also implements ON-DEMAND BRIDGE QUERY:
    Given two concepts, find/build connection path through:
    1. Graph paths (up to 4 hops)
    2. Embedding similarity bridge
    3. LLM bridge hypothesis

CLI usage:
    python -m decoded.connect.worker
    python -m decoded.connect.worker --limit 20 --phase graph
    python -m decoded.connect.worker --bridge "mTOR signaling" "Alzheimer's disease"
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=False)

from decoded.connect.graph_discovery import GraphDiscovery
from decoded.connect.embedding_discovery import EmbeddingDiscovery
from decoded.connect.llm_discovery import LLMDiscovery
from decoded.cost_tracker import CostTracker, CostBudget
from decoded.graph.builder import GraphBuilder, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("decoded.connect.worker")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def get_db_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    psycopg2.extras.register_uuid(conn)
    return conn


def fetch_paper_details(conn, paper_ids: list[str]) -> dict[str, dict]:
    """Fetch full details for a list of paper IDs."""
    if not paper_ids:
        return {}
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    placeholders = ", ".join(["%s"] * len(paper_ids))
    cur.execute(
        f"""
        SELECT p.id, p.title, p.abstract, p.authors, p.doi, p.journal,
               e.entities, e.claims, e.key_findings, e.mechanisms
        FROM raw_papers p
        LEFT JOIN extraction_results e ON e.paper_id = p.id
        WHERE p.id::text IN ({placeholders})
        """,
        paper_ids,
    )
    return {str(r["id"]): dict(r) for r in cur.fetchall()}


def store_connection(conn, connection: dict) -> str:
    """Store a discovered connection to DB. Returns connection id."""
    cur = conn.cursor()
    conn_id = str(uuid4())

    # Canonical ordering: smaller UUID first
    pid_a = str(connection["paper_a_id"])
    pid_b = str(connection["paper_b_id"])
    if pid_a > pid_b:
        pid_a, pid_b = pid_b, pid_a

    cur.execute(
        """
        INSERT INTO discovered_connections (
            id, paper_a_id, paper_b_id, connection_type,
            description, confidence, supporting_evidence,
            shared_entities, novelty_score,
            model_id, prompt_tokens, completion_tokens, cost_usd,
            created_at
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s,
            NOW()
        )
        ON CONFLICT (paper_a_id, paper_b_id, connection_type) DO UPDATE SET
            description = EXCLUDED.description,
            confidence = EXCLUDED.confidence,
            supporting_evidence = EXCLUDED.supporting_evidence,
            novelty_score = EXCLUDED.novelty_score,
            model_id = EXCLUDED.model_id
        RETURNING id
        """,
        (
            conn_id,
            pid_a,
            pid_b,
            connection["connection_type"],
            connection["description"],
            connection["confidence"],
            json.dumps(connection.get("supporting_evidence", [])),
            json.dumps(connection.get("shared_entities", [])),
            connection.get("novelty_score", 0.5),
            connection.get("model_id", "unknown"),
            connection.get("prompt_tokens", 0),
            connection.get("completion_tokens", 0),
            connection.get("cost_usd", 0.0),
        ),
    )
    result = cur.fetchone()
    conn.commit()
    return str(result[0]) if result else conn_id


# ---------------------------------------------------------------------------
# ConnectionWorker
# ---------------------------------------------------------------------------


class ConnectionWorker:
    """Three-phase connection discovery orchestrator."""

    def __init__(
        self,
        limit: int = 50,
        phases: list[str] | None = None,
        daily_budget_usd: float = 10.0,
        total_budget_usd: float = 50.0,
        neo4j_uri: str = NEO4J_URI,
        neo4j_user: str = NEO4J_USER,
        neo4j_password: str = NEO4J_PASSWORD,
    ):
        self.limit = limit
        self.phases = phases or ["graph", "embedding", "llm"]
        self.cost_tracker = CostTracker(
            CostBudget(daily_limit_usd=daily_budget_usd, total_limit_usd=total_budget_usd)
        )
        self._neo4j = (neo4j_uri, neo4j_user, neo4j_password)

    def run(self) -> dict[str, Any]:
        """Run the full connection discovery pipeline."""
        conn = get_db_conn()
        stats = {
            "graph_candidates": 0,
            "embedding_candidates": 0,
            "total_candidates": 0,
            "llm_validated": 0,
            "connections_stored": 0,
            "connections_in_neo4j": 0,
            "errors": 0,
            "cost_usd": 0.0,
        }

        # ---- Phase 1: Graph discovery ----
        candidates = {}
        if "graph" in self.phases:
            logger.info("=== Phase 1: Graph Discovery ===")
            gd = GraphDiscovery(*self._neo4j)
            try:
                graph_candidates = gd.get_all_candidates()
                stats["graph_candidates"] = len(graph_candidates)
                for c in graph_candidates:
                    key = (c["paper_a_id"], c["paper_b_id"])
                    candidates[key] = c
                logger.info("Graph: %d candidates", len(graph_candidates))
            except Exception as exc:
                logger.error("Graph discovery failed: %s", exc)
            finally:
                gd.close()

        # ---- Phase 2: Embedding similarity ----
        if "embedding" in self.phases:
            logger.info("=== Phase 2: Embedding Discovery ===")
            ed = EmbeddingDiscovery(conn, similarity_threshold=0.75, limit=300)
            try:
                # Ensure embeddings exist
                generated = ed.embed_papers_batch()
                logger.info("Generated %d new embeddings", generated)
                emb_candidates = ed.find_similar_pairs()
                stats["embedding_candidates"] = len(emb_candidates)
                for c in emb_candidates:
                    key = (c["paper_a_id"], c["paper_b_id"])
                    if key not in candidates:
                        candidates[key] = c
                    else:
                        candidates[key]["discovery_method"] += ",embedding_similarity"
                logger.info("Embedding: %d new candidates", len(emb_candidates))
            except Exception as exc:
                logger.error("Embedding discovery failed: %s", exc)

        stats["total_candidates"] = len(candidates)
        logger.info("Total unique candidates: %d", len(candidates))

        # ---- Phase 3: LLM validation of top candidates ----
        if "llm" not in self.phases or not candidates:
            return stats

        logger.info("=== Phase 3: LLM Validation ===")
        llm = LLMDiscovery(cost_tracker=self.cost_tracker)

        # Sort by shared_count desc, take top limit
        sorted_candidates = sorted(
            candidates.values(),
            key=lambda x: x.get("shared_count", 0),
            reverse=True,
        )[:self.limit]

        # Collect all unique paper IDs for batch fetch
        all_ids = set()
        for c in sorted_candidates:
            all_ids.add(c["paper_a_id"])
            all_ids.add(c["paper_b_id"])
        paper_details = fetch_paper_details(conn, list(all_ids))

        graph_builder = GraphBuilder(*self._neo4j)
        validated_connections = []

        for candidate in sorted_candidates:
            ok, _ = self.cost_tracker.check_budget()
            if not ok:
                logger.warning("Budget exceeded, stopping LLM validation")
                break

            pid_a = candidate["paper_a_id"]
            pid_b = candidate["paper_b_id"]
            paper_a = paper_details.get(pid_a)
            paper_b = paper_details.get(pid_b)

            if not paper_a or not paper_b:
                continue
            if not paper_a.get("title") or not paper_b.get("title"):
                continue

            try:
                result = llm.validate_pair(
                    paper_a=paper_a,
                    paper_b=paper_b,
                    shared_entities=candidate.get("shared_entities"),
                    discovery_method=candidate.get("discovery_method", "unknown"),
                )
                stats["llm_validated"] += 1

                if result:
                    conn_id = store_connection(conn, result)
                    stats["connections_stored"] += 1
                    validated_connections.append((conn_id, result))

                    # Add edge to Neo4j
                    try:
                        graph_builder.add_connection(
                            paper_a_id=pid_a,
                            paper_b_id=pid_b,
                            connection_type=result["connection_type"],
                            description=result["description"],
                            confidence=result["confidence"],
                            connection_db_id=conn_id,
                        )
                        stats["connections_in_neo4j"] += 1
                    except Exception as exc:
                        logger.warning("Neo4j edge error: %s", exc)

                    logger.info(
                        "Connection: %s <-> %s | %s (%.2f)",
                        str(pid_a)[:8],
                        str(pid_b)[:8],
                        result["connection_type"],
                        result["confidence"],
                    )

            except Exception as exc:
                logger.error("LLM validation error: %s", exc)
                stats["errors"] += 1

        graph_builder.close()
        stats["cost_usd"] = round(self.cost_tracker.total_usd, 4)
        logger.info(
            "Connection discovery complete: %d stored, $%.4f",
            stats["connections_stored"],
            stats["cost_usd"],
        )
        return stats


# ---------------------------------------------------------------------------
# On-demand bridge query
# ---------------------------------------------------------------------------


class BridgeQueryWorker:
    """On-demand bridge: given two concepts, find or build a connection path."""

    def __init__(
        self,
        neo4j_uri: str = NEO4J_URI,
        neo4j_user: str = NEO4J_USER,
        neo4j_password: str = NEO4J_PASSWORD,
    ):
        self._neo4j = (neo4j_uri, neo4j_user, neo4j_password)
        self._conn = get_db_conn()
        self._cost_tracker = CostTracker()

    def query(
        self,
        concept_a: str,
        concept_b: str,
        max_hops: int = 4,
    ) -> dict[str, Any]:
        """Find or build connection between two concepts.

        Returns:
            graph_paths: direct paths through Neo4j (≤4 hops)
            similar_papers: embedding-similarity bridge papers
            hypothesis: LLM-generated bridge hypothesis
        """
        result: dict[str, Any] = {
            "concept_a": concept_a,
            "concept_b": concept_b,
            "graph_paths": [],
            "papers_a": [],
            "papers_b": [],
            "similar_papers": [],
            "hypothesis": None,
        }

        # Step 1: Graph path search
        gd = GraphDiscovery(*self._neo4j)
        try:
            paths = gd.find_bridge_path(concept_a, concept_b, max_hops=max_hops)
            result["graph_paths"] = paths
            logger.info("Found %d graph paths", len(paths))
        except Exception as exc:
            logger.warning("Graph path search failed: %s", exc)
        finally:
            gd.close()

        # Step 2: Find papers related to each concept
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        for concept, key in [(concept_a, "papers_a"), (concept_b, "papers_b")]:
            cur.execute(
                """
                SELECT p.id, p.title, p.abstract, e.key_findings
                FROM raw_papers p
                LEFT JOIN extraction_results e ON e.paper_id = p.id
                WHERE p.title ILIKE %s
                   OR p.abstract ILIKE %s
                LIMIT 10
                """,
                (f"%{concept}%", f"%{concept}%"),
            )
            result[key] = [dict(r) for r in cur.fetchall()]

        # Step 3: Embedding similarity bridge
        ed = EmbeddingDiscovery(self._conn, similarity_threshold=0.65, limit=20)
        if result["papers_a"]:
            first_a = str(result["papers_a"][0]["id"])
            try:
                similar = ed.find_similar_to_paper(first_a, top_k=10)
                result["similar_papers"] = similar
            except Exception as exc:
                logger.warning("Embedding bridge failed: %s", exc)

        # Step 4: LLM bridge hypothesis
        llm = LLMDiscovery(cost_tracker=self._cost_tracker)
        try:
            hyp = llm.generate_bridge_hypothesis(
                concept_a=concept_a,
                concept_b=concept_b,
                papers_a=result["papers_a"],
                papers_b=result["papers_b"],
                graph_paths=result["graph_paths"],
                similar_papers=result["similar_papers"],
            )
            result["hypothesis"] = hyp
        except Exception as exc:
            logger.error("Bridge hypothesis generation failed: %s", exc)

        return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Decoded connection discovery worker"
    )
    parser.add_argument("--limit", type=int, default=50,
                        help="Max candidates to validate with LLM (default: 50)")
    parser.add_argument("--phase", default="graph,embedding,llm",
                        help="Comma-separated phases: graph,embedding,llm")
    parser.add_argument("--daily-budget", type=float, default=10.0)
    parser.add_argument("--total-budget", type=float, default=50.0)
    parser.add_argument("--bridge", nargs=2, metavar=("CONCEPT_A", "CONCEPT_B"),
                        help="Run on-demand bridge query between two concepts")
    args = parser.parse_args()

    if args.bridge:
        concept_a, concept_b = args.bridge
        logger.info("Running bridge query: '%s' <-> '%s'", concept_a, concept_b)
        worker = BridgeQueryWorker()
        result = worker.query(concept_a, concept_b)

        print(f"\n=== Bridge Query: '{concept_a}' <-> '{concept_b}' ===")
        print(f"Graph paths found: {len(result['graph_paths'])}")
        print(f"Papers for A: {len(result['papers_a'])}")
        print(f"Papers for B: {len(result['papers_b'])}")
        print(f"Similar bridge papers: {len(result['similar_papers'])}")
        if result.get("hypothesis"):
            print("\n" + result["hypothesis"]["hypothesis"])
        return

    phases = [p.strip() for p in args.phase.split(",") if p.strip()]
    worker = ConnectionWorker(
        limit=args.limit,
        phases=phases,
        daily_budget_usd=args.daily_budget,
        total_budget_usd=args.total_budget,
    )
    stats = worker.run()

    print("\n=== Connection Discovery Summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
