"""Phase 2: Embedding-based connection discovery via pgvector.

Generates text embeddings for papers (using OpenAI text-embedding-3-small)
and finds semantically similar pairs using cosine similarity in Postgres.
"""

from __future__ import annotations

import json
import logging
import os
from typing import Any

import openai
import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)

EMBEDDING_MODEL = "text-embedding-3-small"
EMBEDDING_DIM = 1536


class EmbeddingDiscovery:
    """Generate + store embeddings; find semantically similar paper pairs."""

    def __init__(
        self,
        db_conn,
        similarity_threshold: float = 0.75,
        limit: int = 500,
    ):
        self._conn = db_conn
        self.similarity_threshold = similarity_threshold
        self.limit = limit
        api_key = os.environ.get("OPENAI_API_KEY")
        self._client = openai.OpenAI(api_key=api_key) if api_key else None

    # ------------------------------------------------------------------
    # Embedding generation
    # ------------------------------------------------------------------

    def _build_paper_text(self, paper: dict) -> str:
        """Create embedding input from paper fields."""
        parts = []
        if paper.get("title"):
            parts.append(f"Title: {paper['title']}")
        if paper.get("abstract"):
            parts.append(f"Abstract: {paper['abstract'][:600]}")

        # Add key findings if extraction exists
        findings = paper.get("key_findings") or []
        if isinstance(findings, str):
            findings = json.loads(findings)
        if findings:
            parts.append("Key findings: " + "; ".join(findings[:3]))

        entities = paper.get("entities") or []
        if isinstance(entities, str):
            entities = json.loads(entities)
        if entities:
            entity_texts = [e.get("text", "") for e in entities[:10] if e.get("text")]
            if entity_texts:
                parts.append("Entities: " + ", ".join(entity_texts))

        return "\n".join(parts)

    def generate_embedding(self, text: str) -> list[float]:
        """Generate embedding vector for text."""
        if not self._client:
            raise RuntimeError("OPENAI_API_KEY not set — cannot generate embeddings")
        response = self._client.embeddings.create(
            model=EMBEDDING_MODEL,
            input=text[:8000],  # token limit safety
        )
        return response.data[0].embedding

    def embed_papers_batch(self, paper_ids: list[str] | None = None) -> int:
        """Generate and store embeddings for papers that lack them.
        Returns number of embeddings generated.
        """
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        if paper_ids:
            placeholders = ", ".join(["%s"] * len(paper_ids))
            cur.execute(
                f"""
                SELECT p.id, p.title, p.abstract,
                       e.id as ext_id, e.key_findings, e.entities
                FROM raw_papers p
                JOIN extraction_results e ON e.paper_id = p.id
                WHERE p.id IN ({placeholders})
                  AND e.embedding IS NULL
                """,
                paper_ids,
            )
        else:
            cur.execute(
                """
                SELECT p.id, p.title, p.abstract,
                       e.id as ext_id, e.key_findings, e.entities
                FROM raw_papers p
                JOIN extraction_results e ON e.paper_id = p.id
                WHERE e.embedding IS NULL
                  AND p.title IS NOT NULL
                LIMIT 200
                """
            )

        papers = [dict(r) for r in cur.fetchall()]
        if not papers:
            logger.info("All papers already have embeddings")
            return 0

        if not self._client:
            logger.warning("OPENAI_API_KEY not set — skipping embedding generation")
            return 0

        logger.info("Generating embeddings for %d papers...", len(papers))
        update_cur = self._conn.cursor()
        generated = 0

        for paper in papers:
            try:
                text = self._build_paper_text(paper)
                embedding = self.generate_embedding(text)
                update_cur.execute(
                    "UPDATE extraction_results SET embedding = %s WHERE id = %s",
                    (embedding, paper["ext_id"]),
                )
                self._conn.commit()
                generated += 1
            except Exception as exc:
                logger.warning("Embedding error for paper %s: %s", paper["id"], exc)
                self._conn.rollback()

        logger.info("Generated %d embeddings", generated)
        return generated

    # ------------------------------------------------------------------
    # Similarity search
    # ------------------------------------------------------------------

    def find_similar_pairs(self) -> list[dict[str, Any]]:
        """Find paper pairs with high cosine similarity using pgvector."""
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Check that we have embeddings to work with
        cur.execute("SELECT count(*) FROM extraction_results WHERE embedding IS NOT NULL")
        n = cur.fetchone()["count"]
        if n < 2:
            logger.warning("Not enough embeddings for similarity search (have %d)", n)
            return []

        logger.info("Running pgvector similarity search over %d embeddings...", n)

        cur.execute(
            """
            SELECT
                a.paper_id AS paper_a_id,
                b.paper_id AS paper_b_id,
                1 - (a.embedding <=> b.embedding) AS similarity,
                'embedding_similarity' AS discovery_method
            FROM extraction_results a
            JOIN extraction_results b
              ON a.paper_id < b.paper_id
            WHERE a.embedding IS NOT NULL
              AND b.embedding IS NOT NULL
              AND 1 - (a.embedding <=> b.embedding) >= %s
            ORDER BY similarity DESC
            LIMIT %s
            """,
            (self.similarity_threshold, self.limit),
        )
        results = cur.fetchall()
        candidates = []
        for r in results:
            candidates.append({
                "paper_a_id": str(r["paper_a_id"]),
                "paper_b_id": str(r["paper_b_id"]),
                "similarity_score": float(r["similarity"]),
                "shared_entities": [],
                "shared_count": round(float(r["similarity"]) * 10),
                "discovery_method": "embedding_similarity",
            })
        logger.info("Embedding discovery found %d candidate pairs", len(candidates))
        return candidates

    def find_similar_to_paper(
        self,
        paper_id: str,
        top_k: int = 20,
    ) -> list[dict[str, Any]]:
        """Find the top-k papers most similar to a given paper."""
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT
                b.paper_id,
                p.title,
                1 - (a.embedding <=> b.embedding) AS similarity
            FROM extraction_results a
            JOIN extraction_results b
              ON b.paper_id <> a.paper_id
            JOIN raw_papers p ON p.id = b.paper_id
            WHERE a.paper_id = %s
              AND a.embedding IS NOT NULL
              AND b.embedding IS NOT NULL
            ORDER BY similarity DESC
            LIMIT %s
            """,
            (paper_id, top_k),
        )
        return [
            {
                "paper_id": str(r["paper_id"]),
                "title": r["title"],
                "similarity": float(r["similarity"]),
            }
            for r in cur.fetchall()
        ]
