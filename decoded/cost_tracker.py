"""LLM cost tracking with per-model pricing."""

from __future__ import annotations

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
# Tracker
# ---------------------------------------------------------------------------

@dataclass
class CostBudget:
    daily_limit_usd: float = 50.0
    total_limit_usd: float = 500.0


class CostTracker:
    """Thread-safe accumulator for LLM spend across the pipeline."""

    def __init__(self, budget: CostBudget | None = None):
        self._budget = budget or CostBudget()
        self._lock = threading.Lock()
        self._records: list[CostRecord] = []
        self._total_usd: float = 0.0
        self._by_model: dict[str, float] = {}
        self._by_task: dict[str, float] = {}

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
            self._total_usd += cost
            self._by_model[model_id] = self._by_model.get(model_id, 0.0) + cost
            self._by_task[task] = self._by_task.get(task, 0.0) + cost

        logger.info(
            "llm_cost",
            model=model_id,
            task=task,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd=round(cost, 6),
            total_usd=round(self._total_usd, 4),
        )
        return record

    # ------------------------------------------------------------------
    # Budget checks
    # ------------------------------------------------------------------

    def check_budget(self) -> tuple[bool, str]:
        """Return (ok, reason). ok=False means budget exceeded."""
        with self._lock:
            if self._total_usd >= self._budget.total_limit_usd:
                return False, f"Total budget exceeded: ${self._total_usd:.2f} >= ${self._budget.total_limit_usd}"
            today_cost = self._today_cost()
            if today_cost >= self._budget.daily_limit_usd:
                return False, f"Daily budget exceeded: ${today_cost:.2f} >= ${self._budget.daily_limit_usd}"
        return True, "ok"

    def _today_cost(self) -> float:
        today = datetime.utcnow().date()
        return sum(r.cost_usd for r in self._records if r.timestamp.date() == today)

    # ------------------------------------------------------------------
    # Reporting
    # ------------------------------------------------------------------

    @property
    def total_usd(self) -> float:
        return self._total_usd

    def summary(self) -> dict:
        with self._lock:
            return {
                "total_usd": round(self._total_usd, 4),
                "today_usd": round(self._today_cost(), 4),
                "budget_daily_usd": self._budget.daily_limit_usd,
                "budget_total_usd": self._budget.total_limit_usd,
                "by_model": {k: round(v, 4) for k, v in self._by_model.items()},
                "by_task": {k: round(v, 4) for k, v in self._by_task.items()},
                "call_count": len(self._records),
            }

    def reset(self) -> None:
        with self._lock:
            self._records.clear()
            self._total_usd = 0.0
            self._by_model.clear()
            self._by_task.clear()


# Module-level singleton for convenience
_tracker: CostTracker | None = None


def get_tracker() -> CostTracker:
    global _tracker
    if _tracker is None:
        _tracker = CostTracker()
    return _tracker
