"""Select high-impact papers for Intelligence Brief generation.

Scoring criteria:
1. Connection count (most-connected papers = highest research leverage)
2. Extraction quality (papers with rich entity/claim data)
3. Not yet critiqued
4. Recency (newer papers preferred)
"""

from __future__ import annotations

import logging
from typing import Any

import psycopg2
import psycopg2.extras

logger = logging.getLogger(__name__)


class CritiqueSelector:
    """Select papers for critique based on impact scoring."""

    def __init__(self, conn):
        self._conn = conn

    def select_for_critique(
        self,
        limit: int = 10,
        min_connections: int = 0,
        model_id: str = "claude-sonnet-4-6",
    ) -> list[dict[str, Any]]:
        """Return top papers to critique, ranked by impact score.

        Impact score = connection_count * 3 + entity_count + claim_count
        Papers already critiqued with this model are excluded.
        """
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            WITH paper_scores AS (
                SELECT
                    p.id,
                    p.title,
                    p.abstract,
                    p.authors,
                    p.doi,
                    p.journal,
                    p.published_date,
                    p.status,
                    -- Connection score
                    COUNT(DISTINCT dc.id) AS connection_count,
                    -- Extraction richness
                    COALESCE(jsonb_array_length(e.entities), 0) AS entity_count,
                    COALESCE(jsonb_array_length(e.claims), 0) AS claim_count,
                    COALESCE(jsonb_array_length(e.key_findings), 0) AS finding_count,
                    e.study_design,
                    e.population,
                    e.primary_outcome,
                    e.key_findings,
                    -- Has extraction?
                    (e.id IS NOT NULL) AS has_extraction,
                    -- Impact score
                    (COUNT(DISTINCT dc.id) * 3
                     + COALESCE(jsonb_array_length(e.entities), 0)
                     + COALESCE(jsonb_array_length(e.claims), 0)) AS impact_score
                FROM raw_papers p
                LEFT JOIN extraction_results e ON e.paper_id = p.id
                LEFT JOIN discovered_connections dc
                    ON dc.paper_a_id = p.id OR dc.paper_b_id = p.id
                WHERE p.title IS NOT NULL
                  AND p.status NOT IN ('error', 'skipped', 'queued')
                  AND NOT EXISTS (
                      SELECT 1 FROM paper_critiques pc
                      WHERE pc.paper_id = p.id AND pc.model_id = %s
                  )
                GROUP BY p.id, p.title, p.abstract, p.authors, p.doi, p.journal,
                         p.published_date, p.status,
                         e.id, e.entities, e.claims, e.key_findings,
                         e.study_design, e.population, e.primary_outcome
                HAVING COUNT(DISTINCT dc.id) >= %s
            )
            SELECT *
            FROM paper_scores
            ORDER BY impact_score DESC, connection_count DESC
            LIMIT %s
            """,
            (model_id, min_connections, limit),
        )
        results = [dict(r) for r in cur.fetchall()]
        logger.info(
            "Selected %d papers for critique (model=%s, min_connections=%d)",
            len(results), model_id, min_connections,
        )
        return results

    def get_connection_context(self, paper_id: str) -> list[dict[str, Any]]:
        """Get all connections for a paper to include in critique context."""
        cur = self._conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(
            """
            SELECT
                dc.connection_type,
                dc.description,
                dc.confidence,
                CASE
                    WHEN dc.paper_a_id = %s THEN p_b.title
                    ELSE p_a.title
                END AS connected_paper_title
            FROM discovered_connections dc
            JOIN raw_papers p_a ON p_a.id = dc.paper_a_id
            JOIN raw_papers p_b ON p_b.id = dc.paper_b_id
            WHERE dc.paper_a_id = %s OR dc.paper_b_id = %s
            ORDER BY dc.confidence DESC
            LIMIT 10
            """,
            (paper_id, paper_id, paper_id),
        )
        return [dict(r) for r in cur.fetchall()]
