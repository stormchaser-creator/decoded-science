"""LLM cost tracking with per-model pricing and persistent daily budgets.

The key design decision: daily spend is tracked in BOTH Redis (fast checks)
and PostgreSQL (source of truth).  On startup, each worker reads today's
actual spend from the DB so that budget limits survive process restarts.
Redis is used for fast inter-process coordination — if Redis is down,
workers fall back to DB-only checks.
"""

from __future__ import annotations

import os
import threading
from dataclasses import dataclass, field
from datetime import datetime
from typing import NamedTuple

import structlog

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Model pricing (USD per 1M tokens, as of 2025)
# ---------------------------------------------------------------------------

class TokenPrice(NamedTuple):
    input_per_1m: float   # USD per 1M input tokens
    output_per_1m: float  # USD per 1M output tokens


MODEL_PRICING: dict[str, TokenPrice] = {
    # Claude 4.x family
    "claude-opus-4-6":          TokenPrice(15.00, 75.00),
    "claude-sonnet-4-6":        TokenPrice(3.00,  15.00),
    "claude-haiku-4-5-20251001": TokenPrice(0.80,   4.00),
    # Claude 3.x (legacy)
    "claude-3-5-sonnet-20241022": TokenPrice(3.00, 15.00),
    "claude-3-5-haiku-20241022":  TokenPrice(0.80,  4.00),
    "claude-3-opus-20240229":     TokenPrice(15.00, 75.00),
    # OpenAI
    "gpt-4o":                   TokenPrice(2.50,  10.00),
    "gpt-4o-mini":              TokenPrice(0.15,   0.60),
    "o1":                       TokenPrice(15.00,  60.00),
    "o1-mini":                  TokenPrice(3.00,   12.00),
}

# Fallback for unknown models
_DEFAULT_PRICING = TokenPrice(3.00, 15.00)

# Redis key prefix for per-task daily spend
_REDIS_DAILY_KEY_PREFIX = "decoded:daily_cost:"


def calculate_cost(model_id: str, input_tokens: int, output_tokens: int) -> float:
    """Return cost in USD for a single LLM call."""
    pricing = MODEL_PRICING.get(model_id, _DEFAULT_PRICING)
    return (input_tokens / 1_000_000 * pricing.input_per_1m +
            output_tokens / 1_000_000 * pricing.output_per_1m)


# ---------------------------------------------------------------------------
# Per-call record
# ---------------------------------------------------------------------------

@dataclass
class CostRecord:
    model_id: str
    task: str               # e.g. "extract", "connect", "critique"
    paper_id: str | None
    input_tokens: int
    output_tokens: int
    cost_usd: float
    timestamp: datetime = field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Persistent helpers
# ---------------------------------------------------------------------------

def _get_redis():
    """Get Redis connection (cached). Returns None if unavailable."""
    try:
        import redis
        url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
        return redis.Redis.from_url(url, decode_responses=True, socket_timeout=2)
    except Exception:
        return None


def _get_today_spend_from_db(task: str | None = None) -> float:
    """Query PostgreSQL for today's LLM spend.

    When *task* is provided, only that task's table is queried so each worker
    tracks its own budget independently.  When task is None, all tables are
    summed (used for reporting only).
    """
    try:
        import psycopg2
        db_url = os.environ.get("DATABASE_URL", "postgresql://localhost/decoded")
        conn = psycopg2.connect(db_url)
        cur = conn.cursor()

        if task == "extract":
            cur.execute("""
                SELECT COALESCE(SUM(cost_usd), 0) FROM extraction_results
                WHERE DATE(created_at) = CURRENT_DATE AND cost_usd > 0
            """)
        elif task == "connect":
            cur.execute("""
                SELECT COALESCE(SUM(cost_usd), 0) FROM discovered_connections
                WHERE DATE(created_at) = CURRENT_DATE AND cost_usd > 0
            """)
        elif task == "critique":
            cur.execute("""
                SELECT COALESCE(SUM(cost_usd), 0) FROM paper_critiques
                WHERE DATE(created_at) = CURRENT_DATE AND cost_usd > 0
            """)
        else:
            # Global fallback: sum all tasks (used when task is unknown/None)
            cur.execute("""
                SELECT COALESCE(SUM(cost), 0) FROM (
                    SELECT cost_usd AS cost FROM extraction_results
                        WHERE DATE(created_at) = CURRENT_DATE AND cost_usd > 0
                    UNION ALL
                    SELECT cost_usd FROM discovered_connections
                        WHERE DATE(created_at) = CURRENT_DATE AND cost_usd > 0
                    UNION ALL
                    SELECT cost_usd FROM paper_critiques
                        WHERE DATE(created_at) = CURRENT_DATE AND cost_usd > 0
                ) t
            """)

        total = float(cur.fetchone()[0])
        conn.close()
        return total
    except Exception as exc:
        logger.warning("cost_tracker_db_read_failed", error=str(exc))
        return 0.0


def _redis_daily_key(task: str | None = None) -> str:
    # Use local date (not UTC) to match PostgreSQL's CURRENT_DATE (which uses server local time).
    # Using UTC caused a mismatch: evening extractions (local) fell on the next UTC day, so
    # the Redis key accumulated $50 before local midnight, blocking the next local day's work.
    date = datetime.now().strftime("%Y-%m-%d")
    if task:
        return f"{_REDIS_DAILY_KEY_PREFIX}{task}:{date}"
    return _REDIS_DAILY_KEY_PREFIX + date


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------

@dataclass
class CostBudget:
    daily_limit_usd: float = 10.0
    total_limit_usd: float = 100.0


class CostTracker:
    """Thread-safe accumulator for LLM spend with persistent budget enforcement.

    Pass *task* (e.g. "extract", "connect", "critique") so each worker tracks
    its own daily spend independently.  Without a task, the global sum of all
    workers is used — which causes workers to block each other when any single
    worker exhausts the full pipeline budget.

    On init, reads today's actual spend from PostgreSQL so budget limits
    survive process restarts.  Each record() call also increments a task-scoped
    Redis counter for fast inter-process coordination.
    """

    def __init__(self, budget: CostBudget | None = None, task: str | None = None):
        self._budget = budget or CostBudget()
        self._task = task  # None → global (legacy behaviour)
        self._lock = threading.Lock()
        self._records: list[CostRecord] = []
        self._session_usd: float = 0.0       # this process only
        self._by_model: dict[str, float] = {}
        self._by_task: dict[str, float] = {}
        self._redis = _get_redis()

        # Seed from DB so we know what was already spent today (task-scoped)
        self._prior_today_usd = _get_today_spend_from_db(task=self._task)
        logger.info(
            "cost_tracker_init",
            task=self._task or "global",
            prior_today_usd=round(self._prior_today_usd, 2),
            daily_limit=self._budget.daily_limit_usd,
            total_limit=self._budget.total_limit_usd,
        )

        # Sync Redis counter to DB truth (if Redis is behind)
        if self._redis:
            try:
                key = _redis_daily_key(self._task)
                current = float(self._redis.get(key) or 0)
                if current < self._prior_today_usd:
                    # Redis is behind (maybe it was flushed) — set to DB value
                    self._redis.set(key, str(self._prior_today_usd))
                    self._redis.expire(key, 90000)  # ~25 hours TTL
            except Exception:
                pass

    # ------------------------------------------------------------------
    # Recording
    # ------------------------------------------------------------------

    def record(
        self,
        model_id: str,
        task: str,
        input_tokens: int,
        output_tokens: int,
        paper_id: str | None = None,
    ) -> CostRecord:
        cost = calculate_cost(model_id, input_tokens, output_tokens)
        record = CostRecord(
            model_id=model_id,
            task=task,
            paper_id=paper_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=cost,
        )
        with self._lock:
            self._records.append(record)
            self._session_usd += cost
            self._by_model[model_id] = self._by_model.get(model_id, 0.0) + cost
            self._by_task[task] = self._by_task.get(task, 0.0) + cost

        # Atomically increment task-scoped Redis daily counter
        if self._redis:
            try:
                key = _redis_daily_key(self._task)
                self._redis.incrbyfloat(key, cost)
                self._redis.expire(key, 90000)  # renew TTL ~25h
            except Exception:
                pass  # Redis failure is non-fatal; DB is truth

        logger.info(
            "llm_cost",
            model=model_id,
            task=task,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost, 6),
            session_usd=round(self._session_usd, 4),
            today_usd=round(self.today_usd, 2),
        )
        return record

    # ------------------------------------------------------------------
    # Budget checks
    # ------------------------------------------------------------------

    @property
    def today_usd(self) -> float:
        """Today's spend for this task: prior (from DB at init) + this session."""
        # Try task-scoped Redis key first
        if self._redis:
            try:
                val = self._redis.get(_redis_daily_key(self._task))
                if val is not None:
                    return float(val)
            except Exception:
                pass
        # Fallback: DB seed + this session
        return self._prior_today_usd + self._session_usd

    @property
    def total_usd(self) -> float:
        return self._session_usd

    def check_budget(self) -> tuple[bool, str]:
        """Return (ok, reason). ok=False means budget exceeded."""
        today = self.today_usd
        if today >= self._budget.daily_limit_usd:
            return False, (
                f"Daily budget exceeded: ${today:.2f} >= "
                f"${self._budget.daily_limit_usd:.2f} "
                f"(across all workers today)"
            )
        if self._session_usd >= self._budget.total_limit_usd:
            return False, (
                f"Session budget exceeded: ${self._session_usd:.2f} >= "
                f"${self._budget.total_limit_usd}"
            )
        return True, "ok"

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    def summary(self) -> dict:
        with self._lock:
            return {
                "session_usd": round(self._session_usd, 4),
                "today_usd": round(self.today_usd, 4),
                "total_usd": round(self._session_usd, 4),  # compat
                "budget_daily_usd": self._budget.daily_limit_usd,
                "budget_total_usd": self._budget.total_limit_usd,
                "by_model": {k: round(v, 4) for k, v in self._by_model.items()},
                "by_task": {k: round(v, 4) for k, v in self._by_task.items()},
                "call_count": len(self._records),
            }

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._session_usd = 0.0
            self._by_model.clear()
            self._by_task.clear()


# Module-level singleton for convenience
_tracker: CostTracker | None = None


def get_tracker() -> CostTracker:
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker
