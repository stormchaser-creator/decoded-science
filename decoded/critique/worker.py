"""Critique worker — select and critique high-impact papers.

CLI usage:
    python -m decoded.critique.worker
    python -m decoded.critique.worker --limit 5
    python -m decoded.critique.worker --paper-id <uuid>
    python -m decoded.critique.worker --min-connections 1
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=False)

from decoded.critique.selector import CritiqueSelector
from decoded.critique.generator import CritiqueGenerator, CRITIQUE_MODEL
from decoded.cost_tracker import CostTracker, CostBudget

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("decoded.critique.worker")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def get_db_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    psycopg2.extras.register_uuid(conn)
    return conn


def fetch_paper_by_id(conn, paper_id: str) -> dict | None:
    """Fetch a specific paper with extraction data."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT p.id, p.title, p.abstract, p.authors, p.doi, p.journal,
               p.published_date, p.status,
               e.study_design, e.population, e.primary_outcome,
               e.key_findings, e.entities, e.claims
        FROM raw_papers p
        LEFT JOIN extraction_results e ON e.paper_id = p.id
        WHERE p.id = %s
        """,
        (paper_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def store_critique(conn, critique) -> str:
    """Store a PaperCritique to DB. Returns stored id."""
    cur = conn.cursor()

    def to_json(val) -> str:
        if isinstance(val, list):
            return json.dumps(val)
        return json.dumps(val or [])

    cur.execute(
        """
        INSERT INTO paper_critiques (
            id, paper_id, model_id,
            overall_quality, methodology_score, reproducibility_score,
            novelty_score, statistical_rigor,
            strengths, weaknesses, red_flags,
            summary, recommendation,
            prompt_tokens, completion_tokens, cost_usd,
            created_at
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            %s, %s,
            %s, %s, %s,
            NOW()
        )
        ON CONFLICT (paper_id, model_id) DO UPDATE SET
            overall_quality = EXCLUDED.overall_quality,
            methodology_score = EXCLUDED.methodology_score,
            reproducibility_score = EXCLUDED.reproducibility_score,
            novelty_score = EXCLUDED.novelty_score,
            statistical_rigor = EXCLUDED.statistical_rigor,
            strengths = EXCLUDED.strengths,
            weaknesses = EXCLUDED.weaknesses,
            red_flags = EXCLUDED.red_flags,
            summary = EXCLUDED.summary,
            recommendation = EXCLUDED.recommendation,
            prompt_tokens = EXCLUDED.prompt_tokens,
            completion_tokens = EXCLUDED.completion_tokens,
            cost_usd = EXCLUDED.cost_usd
        RETURNING id
        """,
        (
            str(critique.id),
            str(critique.paper_id),
            critique.model_id,
            critique.overall_quality,
            critique.methodology_score,
            critique.reproducibility_score,
            critique.novelty_score,
            critique.statistical_rigor,
            to_json(critique.strengths),
            to_json(critique.weaknesses),
            to_json(critique.red_flags),
            critique.summary,
            critique.recommendation,
            critique.prompt_tokens,
            critique.completion_tokens,
            critique.cost_usd,
        ),
    )
    result = cur.fetchone()
    conn.commit()
    return str(result[0]) if result else str(critique.id)


# ---------------------------------------------------------------------------
# CritiqueWorker
# ---------------------------------------------------------------------------


class CritiqueWorker:
    """Select and critique high-impact papers."""

    def __init__(
        self,
        model_id: str = CRITIQUE_MODEL,
        limit: int = 10,
        min_connections: int = 0,
        paper_id: str | None = None,
        daily_budget_usd: float = 10.0,
        total_budget_usd: float = 50.0,
    ):
        self.model_id = model_id
        self.limit = limit
        self.min_connections = min_connections
        self.paper_id = paper_id
        self.cost_tracker = CostTracker(
            CostBudget(daily_limit_usd=daily_budget_usd, total_limit_usd=total_budget_usd)
        )

    def run(self) -> dict[str, Any]:
        """Run critique generation. Returns stats."""
        conn = get_db_conn()
        selector = CritiqueSelector(conn)
        generator = CritiqueGenerator(
            model_id=self.model_id,
            cost_tracker=self.cost_tracker,
        )

        stats = {
            "total": 0,
            "critiqued": 0,
            "high_quality": 0,
            "medium_quality": 0,
            "low_quality": 0,
            "errors": 0,
            "cost_usd": 0.0,
        }

        # Select papers
        if self.paper_id:
            paper = fetch_paper_by_id(conn, self.paper_id)
            papers = [paper] if paper else []
        else:
            papers = selector.select_for_critique(
                limit=self.limit,
                min_connections=self.min_connections,
                model_id=self.model_id,
            )

        stats["total"] = len(papers)
        logger.info("Critiquing %d papers...", len(papers))

        for paper in papers:
            ok, reason = self.cost_tracker.check_budget()
            if not ok:
                logger.warning("Budget exceeded: %s", reason)
                break

            paper_id = str(paper["id"])
            title = paper.get("title", "Unknown")[:70]

            try:
                # Get connection context
                connections = selector.get_connection_context(paper_id)

                # Generate critique
                critique = generator.generate(paper, connections)

                # Store
                store_critique(conn, critique)
                stats["critiqued"] += 1
                stats[f"{critique.overall_quality}_quality"] += 1

                logger.info(
                    "Critiqued %s | %s quality | rec: %s | $%.4f",
                    title,
                    critique.overall_quality,
                    critique.recommendation,
                    critique.cost_usd,
                )

            except Exception as exc:
                logger.error("Critique failed for %s: %s", paper_id, exc, exc_info=True)
                stats["errors"] += 1

        stats["cost_usd"] = round(self.cost_tracker.total_usd, 4)
        return stats


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Decoded critique worker — Intelligence Brief generation"
    )
    parser.add_argument("--limit", type=int, default=10,
                        help="Max papers to critique (default: 10)")
    parser.add_argument("--model", default=CRITIQUE_MODEL,
                        help=f"Claude model (default: {CRITIQUE_MODEL})")
    parser.add_argument("--paper-id", default=None,
                        help="Critique a specific paper by UUID")
    parser.add_argument("--min-connections", type=int, default=0,
                        help="Min connection count to select paper (default: 0)")
    parser.add_argument("--daily-budget", type=float, default=10.0)
    parser.add_argument("--total-budget", type=float, default=50.0)
    args = parser.parse_args()

    worker = CritiqueWorker(
        model_id=args.model,
        limit=args.limit,
        min_connections=args.min_connections,
        paper_id=args.paper_id,
        daily_budget_usd=args.daily_budget,
        total_budget_usd=args.total_budget,
    )
    stats = worker.run()

    print("\n=== Critique Summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Show results
    conn = get_db_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT pc.overall_quality, pc.recommendation, pc.summary,
               pc.methodology_score, p.title
        FROM paper_critiques pc
        JOIN raw_papers p ON p.id = pc.paper_id
        ORDER BY pc.created_at DESC
        LIMIT 5
        """
    )
    rows = cur.fetchall()
    if rows:
        print("\n=== Recent Critiques ===")
        for r in rows:
            print(f"\n  [{r['overall_quality'].upper()}] {r['title'][:70]}")
            print(f"  Methodology: {r['methodology_score']}/10 | Rec: {r['recommendation']}")
            print(f"  {r['summary'][:150]}...")


if __name__ == "__main__":
    main()
