"""Backfill typed triples and operation tags on already-extracted papers.

Pearl audit (2026-04-15): subject/predicate/object in claims are 100% NULL for all
existing extractions because the old prompt never requested them. This script re-runs
extraction on papers that already have extraction_results but are missing primary_operation,
using the same paper text — just re-extracting with the updated prompt.

Estimated cost: ~$0.003/paper = ~$72 for 24K papers.
Budget default: $50 (covers ~16K papers per run; run twice to cover all).

CLI usage:
    python -m decoded.extract.backfill --limit 100  # dry-run to verify
    python -m decoded.extract.backfill --limit 5000 --budget 15.0
    python -m decoded.extract.backfill              # full backfill ($50 budget)
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=True)

from decoded.cost_tracker import CostTracker, CostBudget
from decoded.extract.extractor import PaperExtractor, DEFAULT_MODEL
from decoded.extract.worker import _sync_claims_to_table

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("decoded.extract.backfill")


def get_db_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    psycopg2.extras.register_uuid(conn)
    return conn


def fetch_papers_for_backfill(conn, limit: int) -> list[dict]:
    """Fetch papers that have extraction_results but are missing primary_operation.

    These are the papers extracted before the 2026-04-15 prompt update — they
    have flat claim text but no typed triples or operation tags.
    """
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT
            p.id, p.title, p.abstract, p.full_text, p.sections,
            er.id AS extraction_id, er.model_id
        FROM extraction_results er
        JOIN raw_papers p ON p.id = er.paper_id
        WHERE er.primary_operation IS NULL
          AND p.title IS NOT NULL
        ORDER BY
            CASE WHEN p.full_text IS NOT NULL THEN 0 ELSE 1 END,
            er.created_at DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]


def update_extraction_result(conn, extraction_id: str, result) -> None:
    """Patch existing extraction_result row with typed triple fields + operation tags."""
    cur = conn.cursor()

    def jsonify(obj) -> str:
        if hasattr(obj, "__iter__") and not isinstance(obj, str):
            return json.dumps([
                item.model_dump() if hasattr(item, "model_dump") else item
                for item in obj
            ])
        return json.dumps(obj)

    cur.execute(
        """
        UPDATE extraction_results SET
            claims = %s,
            mechanisms = %s,
            primary_operation = %s,
            secondary_operations = %s,
            operation_confidence = %s,
            operation_reasoning = %s
        WHERE id = %s
        """,
        (
            jsonify(result.claims),
            jsonify(result.mechanisms),
            result.primary_operation,
            result.secondary_operations if result.secondary_operations else [],
            result.operation_confidence,
            result.operation_reasoning,
            extraction_id,
        ),
    )
    conn.commit()


class BackfillWorker:
    """Re-extract typed triples and operation tags for already-extracted papers."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        limit: int = 5000,
        concurrency: int = 5,
        budget_usd: float = 50.0,
    ):
        self.model_id = model_id
        self.limit = limit
        self.concurrency = concurrency
        self.budget_usd = budget_usd
        self.extractor = PaperExtractor(model_id=model_id)
        self.cost_tracker = CostTracker(
            CostBudget(daily_limit_usd=budget_usd, total_limit_usd=budget_usd),
            task="backfill",
        )

    def run(self) -> dict:
        conn = get_db_conn()
        papers = fetch_papers_for_backfill(conn, limit=self.limit)

        logger.info(
            "Backfill: %d papers need typed triples + operation tags (model=%s, budget=$%.2f)",
            len(papers), self.model_id, self.budget_usd,
        )

        if not papers:
            logger.info("Nothing to backfill — all papers already have primary_operation set.")
            return {"total": 0, "updated": 0, "errors": 0, "cost_usd": 0.0}

        stats = {"total": len(papers), "updated": 0, "errors": 0, "skipped": 0}

        with ThreadPoolExecutor(max_workers=self.concurrency) as pool:
            futures = {
                pool.submit(self._process_paper, conn, paper): paper
                for paper in papers
            }
            for future in as_completed(futures):
                paper = futures[future]
                try:
                    outcome = future.result()
                    stats[outcome] = stats.get(outcome, 0) + 1
                except Exception as exc:
                    logger.error("Unhandled error for paper %s: %s", paper.get("id"), exc)
                    stats["errors"] += 1

        cost_summary = self.cost_tracker.summary()
        stats["cost_usd"] = cost_summary["total_usd"]
        logger.info(
            "Backfill complete: %d updated, %d errors, %d skipped | $%.4f total",
            stats["updated"], stats["errors"], stats.get("skipped", 0), stats["cost_usd"],
        )
        return stats

    def _process_paper(self, conn, paper: dict) -> str:
        paper_id = str(paper["id"])
        extraction_id = str(paper["extraction_id"])

        ok, reason = self.cost_tracker.check_budget()
        if not ok:
            logger.warning("Budget exceeded, stopping: %s", reason)
            return "skipped"

        title = paper.get("title", "")
        abstract = paper.get("abstract")
        full_text = paper.get("full_text")
        sections = paper.get("sections")

        if isinstance(sections, str):
            try:
                sections = json.loads(sections)
            except Exception:
                sections = {}

        if not abstract and not full_text and not sections:
            logger.debug("Skipping %s — no content", paper_id)
            return "skipped"

        try:
            result = self.extractor.extract(
                paper_id=paper_id,
                title=title,
                abstract=abstract,
                full_text=full_text,
                sections=sections or {},
            )

            self.cost_tracker.record(
                model_id=self.model_id,
                task="backfill",
                input_tokens=result.prompt_tokens,
                output_tokens=result.completion_tokens,
                paper_id=paper_id,
            )

            # Update the existing extraction_results row with new typed fields
            update_extraction_result(conn, extraction_id=extraction_id, result=result)

            # Sync enriched claims to the claims table
            cur = conn.cursor()
            _sync_claims_to_table(cur, paper_id=paper_id, result=result)
            conn.commit()

            triple_count = sum(
                1 for c in result.claims
                if c.subject and c.predicate and c.object
            )
            op_str = result.primary_operation or "untagged"

            logger.info(
                "Backfilled %s: op=%s, %d/%d claims with triples, $%.5f",
                paper_id[:8], op_str, triple_count, len(result.claims), result.cost_usd,
            )
            return "updated"

        except Exception as exc:
            logger.warning("Backfill failed for %s: %s", paper_id, exc, exc_info=True)
            return "errors"


def main():
    parser = argparse.ArgumentParser(
        description="Backfill typed claim triples + operation tags on already-extracted papers"
    )
    parser.add_argument("--limit", type=int, default=5000,
                        help="Max papers to backfill per run (default: 5000)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Claude model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="Parallel LLM calls (default: 5)")
    parser.add_argument("--budget", type=float, default=50.0,
                        help="Total spend limit for this backfill run in USD (default: 50.0)")
    args = parser.parse_args()

    worker = BackfillWorker(
        model_id=args.model,
        limit=args.limit,
        concurrency=args.concurrency,
        budget_usd=args.budget,
    )
    stats = worker.run()

    print("\n=== Backfill Summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Quick verification query
    import subprocess
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@Whits-Mac-mini.local:5432/encoded_human")
    try:
        result = subprocess.run(
            ["psql", db_url, "-c",
             """SELECT
                 COUNT(*) FILTER (WHERE primary_operation IS NOT NULL) AS with_op,
                 COUNT(*) AS total,
                 ROUND(100.0 * COUNT(*) FILTER (WHERE primary_operation IS NOT NULL) / NULLIF(COUNT(*), 0), 1) AS pct
               FROM extraction_results;"""],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode == 0:
            print("\n=== DB Verification ===")
            print(result.stdout)
    except Exception:
        pass


if __name__ == "__main__":
    main()
