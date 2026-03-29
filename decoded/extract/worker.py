"""ExtractionWorker: run LLM extraction on ingested papers.

CLI usage:
    python -m decoded.extract.worker --limit 10
    python -m decoded.extract.worker --limit 50 --model claude-haiku-4-5-20251001
    python -m decoded.extract.worker --status parsed --limit 20
    python -m decoded.extract.worker --paper-id <uuid>
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import os
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=True)

from decoded.cost_tracker import CostTracker, CostBudget
from decoded.extract.extractor import PaperExtractor, DEFAULT_MODEL

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("decoded.extract.worker")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------


def get_db_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    psycopg2.extras.register_uuid(conn)
    return conn


def fetch_papers_for_extraction(
    conn,
    status_filter: list[str],
    limit: int,
    paper_id: str | None = None,
) -> list[dict]:
    """Fetch papers ready for extraction."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    if paper_id:
        cur.execute(
            """
            SELECT p.id, p.title, p.abstract, p.full_text, p.sections, p.pub_year,
                   p.authors, p.journal, p.doi, p.pmc_id, p.status
            FROM raw_papers p
            LEFT JOIN extraction_results e ON e.paper_id = p.id
            WHERE p.id = %s AND e.id IS NULL
            """,
            (paper_id,),
        )
    else:
        placeholders = ", ".join(["%s"] * len(status_filter))
        cur.execute(
            f"""
            SELECT p.id, p.title, p.abstract, p.full_text, p.sections, p.pub_year,
                   p.authors, p.journal, p.doi, p.pmc_id, p.status
            FROM raw_papers p
            LEFT JOIN extraction_results e ON e.paper_id = p.id
            WHERE p.status IN ({placeholders})
              AND e.id IS NULL
              AND p.title IS NOT NULL
              AND (p.abstract IS NOT NULL AND LENGTH(p.abstract) >= 100)
            ORDER BY
                CASE WHEN p.full_text IS NOT NULL THEN 0 ELSE 1 END,
                CASE p.status
                    WHEN 'parsed' THEN 0
                    WHEN 'fetched' THEN 1
                    ELSE 2
                END,
                p.pub_year DESC NULLS LAST
            LIMIT %s
            """,
            (*status_filter, limit),
        )
    return [dict(r) for r in cur.fetchall()]


def mark_extracting(conn, paper_id: str):
    cur = conn.cursor()
    cur.execute(
        "UPDATE raw_papers SET status='extracting', updated_at=NOW() WHERE id=%s",
        (str(paper_id),),
    )
    conn.commit()


def store_extraction(conn, result, paper_id: str):
    """Insert extraction result and update paper status."""
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
        INSERT INTO extraction_results (
            id, paper_id, model_id,
            study_design, sample_size, population, intervention, comparator,
            primary_outcome, secondary_outcomes,
            entities, claims, mechanisms, methods,
            key_findings, limitations, funding_sources, conflicts_of_interest,
            prompt_tokens, completion_tokens, cost_usd,
            created_at
        ) VALUES (
            %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s, %s,
            %s, %s, %s,
            NOW()
        )
        ON CONFLICT (paper_id, model_id) DO UPDATE SET
            study_design = EXCLUDED.study_design,
            sample_size = EXCLUDED.sample_size,
            population = EXCLUDED.population,
            intervention = EXCLUDED.intervention,
            comparator = EXCLUDED.comparator,
            primary_outcome = EXCLUDED.primary_outcome,
            secondary_outcomes = EXCLUDED.secondary_outcomes,
            entities = EXCLUDED.entities,
            claims = EXCLUDED.claims,
            mechanisms = EXCLUDED.mechanisms,
            methods = EXCLUDED.methods,
            key_findings = EXCLUDED.key_findings,
            limitations = EXCLUDED.limitations,
            funding_sources = EXCLUDED.funding_sources,
            conflicts_of_interest = EXCLUDED.conflicts_of_interest,
            prompt_tokens = EXCLUDED.prompt_tokens,
            completion_tokens = EXCLUDED.completion_tokens,
            cost_usd = EXCLUDED.cost_usd
        """,
        (
            str(result.id),
            str(paper_id),
            result.model_id,
            result.study_design if isinstance(result.study_design, str) else result.study_design.value,
            result.sample_size,
            result.population,
            result.intervention,
            result.comparator,
            result.primary_outcome,
            jsonify(result.secondary_outcomes),
            jsonify(result.entities),
            jsonify(result.claims),
            jsonify(result.mechanisms),
            jsonify(result.methods),
            json.dumps(result.key_findings),
            json.dumps(result.limitations),
            json.dumps(result.funding_sources),
            result.conflicts_of_interest,
            result.prompt_tokens,
            result.completion_tokens,
            result.cost_usd,
        ),
    )

    cur.execute(
        "UPDATE raw_papers SET status='extracted', updated_at=NOW() WHERE id=%s",
        (str(paper_id),),
    )
    conn.commit()


def mark_error(conn, paper_id: str, error: str):
    cur = conn.cursor()
    cur.execute(
        """UPDATE raw_papers
           SET status='error',
               raw_metadata = raw_metadata || %s,
               updated_at = NOW()
           WHERE id = %s""",
        (json.dumps({"extract_error": error[:500]}), str(paper_id)),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# ExtractionWorker
# ---------------------------------------------------------------------------


class ExtractionWorker:
    """Run LLM extraction on papers from the DB."""

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        limit: int = 50,
        concurrency: int = 5,
        status_filter: list[str] | None = None,
        paper_id: str | None = None,
        daily_budget_usd: float = 10.0,
        total_budget_usd: float = 50.0,
    ):
        self.model_id = model_id
        self.limit = limit
        self.concurrency = concurrency
        self.status_filter = status_filter or ["fetched", "parsed"]
        self.paper_id = paper_id
        self.extractor = PaperExtractor(model_id=model_id)
        self.cost_tracker = CostTracker(
            CostBudget(daily_limit_usd=daily_budget_usd, total_limit_usd=total_budget_usd)
        )

    def run(self) -> dict[str, Any]:
        """Run extraction. Returns stats dict."""
        conn = get_db_conn()

        papers = fetch_papers_for_extraction(
            conn,
            status_filter=self.status_filter,
            limit=self.limit,
            paper_id=self.paper_id,
        )

        logger.info(
            "Found %d papers for extraction (model=%s)",
            len(papers), self.model_id,
        )

        stats = {"total": len(papers), "extracted": 0, "errors": 0, "skipped": 0}

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
        logger.info(
            "Extraction complete: %d extracted, %d errors | $%.4f total",
            stats["extracted"], stats["errors"], cost_summary["total_usd"],
        )
        stats["cost_usd"] = cost_summary["total_usd"]
        return stats

    def _process_paper(self, conn, paper: dict) -> str:
        """Extract one paper. Returns 'extracted', 'errors', or 'skipped'."""
        paper_id = str(paper["id"])

        # Budget check
        ok, reason = self.cost_tracker.check_budget()
        if not ok:
            logger.warning("Budget exceeded, stopping: %s", reason)
            return "skipped"

        title = paper.get("title", "")
        abstract = paper.get("abstract")
        full_text = paper.get("full_text")
        sections = paper.get("sections")

        # sections may come back as dict or string from psycopg2
        if isinstance(sections, str):
            try:
                import json as _json
                sections = _json.loads(sections)
            except Exception:
                sections = {}

        # Skip papers with no usable content
        if not abstract and not full_text and not sections:
            logger.debug("Skipping %s — no content", paper_id)
            return "skipped"

        try:
            mark_extracting(conn, paper_id)

            result = self.extractor.extract(
                paper_id=paper_id,
                title=title,
                abstract=abstract,
                full_text=full_text,
                sections=sections or {},
            )

            self.cost_tracker.record(
                model_id=self.model_id,
                task="extract",
                input_tokens=result.prompt_tokens,
                output_tokens=result.completion_tokens,
                paper_id=paper_id,
            )

            store_extraction(conn, result, paper_id)

            # Bridge to Pearl KB — write claims/mechanisms/findings as kb_entries
            try:
                from decoded.pearl.bridge import bridge_extraction_to_pearl
                bridge_stats = bridge_extraction_to_pearl(result, paper, conn)
                conn.commit()
            except Exception as bridge_exc:
                logger.warning("Pearl bridge failed for %s: %s", paper_id[:8], bridge_exc)
                bridge_stats = {}

            logger.info(
                "Extracted %s: %s (%d entities, %d claims, $%.4f) | pearl +%d entries",
                paper_id[:8],
                title[:60],
                len(result.entities),
                len(result.claims),
                result.cost_usd,
                bridge_stats.get("total", 0),
            )
            return "extracted"

        except Exception as exc:
            logger.warning("Extraction failed for %s: %s", paper_id, exc, exc_info=True)
            try:
                mark_error(conn, paper_id, str(exc))
            except Exception:
                pass
            return "errors"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="Decoded extraction worker — LLM extraction on ingested papers"
    )
    parser.add_argument("--limit", type=int, default=50,
                        help="Max papers to extract (default: 50)")
    parser.add_argument("--model", default=DEFAULT_MODEL,
                        help=f"Claude model to use (default: {DEFAULT_MODEL})")
    parser.add_argument("--status", default="fetched,parsed",
                        help="Comma-separated statuses to process (default: fetched,parsed)")
    parser.add_argument("--paper-id", default=None,
                        help="Extract a specific paper by UUID")
    parser.add_argument("--concurrency", type=int, default=5,
                        help="Parallel LLM calls (default: 5)")
    parser.add_argument("--daily-budget", type=float, default=10.0,
                        help="Daily spend limit in USD (default: 10.0)")
    parser.add_argument("--total-budget", type=float, default=50.0,
                        help="Total spend limit in USD (default: 50.0)")
    args = parser.parse_args()

    status_filter = [s.strip() for s in args.status.split(",") if s.strip()]

    worker = ExtractionWorker(
        model_id=args.model,
        limit=args.limit,
        concurrency=args.concurrency,
        status_filter=status_filter,
        paper_id=args.paper_id,
        daily_budget_usd=args.daily_budget,
        total_budget_usd=args.total_budget,
    )
    stats = worker.run()

    print("\n=== Extraction Summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")

    # Exponential backoff when queue is empty to prevent crash-loop restarts
    if stats.get("total", 0) == 0:
        import time
        backoff = int(os.environ.get("DECODE_EMPTY_BACKOFF", "60"))
        logger.info("No papers to extract — sleeping %ds before exit (PM2 restart_delay handles backoff)", backoff)
        time.sleep(backoff)
    elif stats.get("extracted", 0) == 0 and stats.get("errors", 0) > 0:
        import time
        backoff = int(os.environ.get("DECODE_ERROR_BACKOFF", "30"))
        logger.warning("All papers errored — sleeping %ds before exit", backoff)
        time.sleep(backoff)


if __name__ == "__main__":
    main()
