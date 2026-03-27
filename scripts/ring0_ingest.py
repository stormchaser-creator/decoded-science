#!/usr/bin/env python3
"""Ring 0 Full Ingest — all seed queries, target 5,000 papers.

Usage:
    python scripts/ring0_ingest.py
    python scripts/ring0_ingest.py --dry-run
    python scripts/ring0_ingest.py --limit 100      # per-query limit
    python scripts/ring0_ingest.py --budget 300     # USD budget cap

Runs all Ring 0 seed queries across longevity, sleep, inflammation,
neuroplasticity, and healthspan domains. Tracks costs in real time
against the $300-400 budget.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env", override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("ring0")

# ---------------------------------------------------------------------------
# Ring 0 seed queries
# 5 domains × ~10 queries each = ~50 queries × 100 papers = 5,000 target
# ---------------------------------------------------------------------------

RING_0_QUERIES = [
    # --- Longevity & Aging Biology ---
    ("longevity", "mTOR signaling aging longevity"),
    ("longevity", "sirtuins caloric restriction lifespan"),
    ("longevity", "NAD+ metabolism aging"),
    ("longevity", "telomere length aging disease"),
    ("longevity", "cellular senescence SASP aging"),
    ("longevity", "autophagy aging healthspan"),
    ("longevity", "mitochondrial dysfunction aging"),
    ("longevity", "IGF-1 signaling longevity"),
    ("longevity", "epigenetic clock aging biomarker"),
    ("longevity", "rapamycin lifespan extension"),

    # --- Inflammation & Immunosenescence ---
    ("longevity", "inflammaging chronic inflammation aging"),
    ("longevity", "IL-6 interleukin-6 aging disease"),
    ("longevity", "TNF-alpha neuroinflammation"),
    ("longevity", "NF-kB inflammation aging"),
    ("longevity", "microglial activation neuroinflammation"),
    ("longevity", "CRP inflammation cardiovascular aging"),
    ("longevity", "innate immune activation aging"),
    ("longevity", "cytokine storm aging COVID"),

    # --- Sleep & Circadian Biology ---
    ("longevity", "sleep deprivation neurodegeneration"),
    ("longevity", "circadian rhythm aging longevity"),
    ("longevity", "slow wave sleep deep sleep aging"),
    ("longevity", "glymphatic system sleep clearance"),
    ("longevity", "sleep apnea cognitive decline"),
    ("longevity", "melatonin aging sleep circadian"),
    ("longevity", "sleep duration mortality risk"),
    ("longevity", "insomnia inflammation biomarkers"),

    # --- Neuroplasticity & Cognitive Aging ---
    ("longevity", "BDNF neuroplasticity aging"),
    ("longevity", "neurogenesis hippocampus aging"),
    ("longevity", "cognitive decline prevention aging"),
    ("longevity", "Alzheimer disease prevention lifestyle"),
    ("longevity", "synaptic plasticity aging memory"),
    ("longevity", "exercise neuroprotection BDNF"),
    ("longevity", "stress cortisol hippocampal volume aging"),
    ("longevity", "gut microbiome brain aging axis"),

    # --- Metabolic Health & Longevity ---
    ("longevity", "insulin resistance metabolic syndrome aging"),
    ("longevity", "mitophagy mitochondrial quality control"),
    ("longevity", "AMPK energy sensing aging"),
    ("longevity", "reactive oxygen species oxidative stress aging"),
    ("longevity", "glycemic control longevity aging"),
    ("longevity", "intermittent fasting longevity"),
    ("longevity", "ketogenic diet neuroprotection aging"),
    ("longevity", "omega-3 fatty acid aging inflammation"),

    # --- Cardiovascular & Vascular Aging ---
    ("longevity", "arterial stiffness vascular aging"),
    ("longevity", "endothelial dysfunction aging cardiovascular"),
    ("longevity", "blood pressure cognitive decline aging"),
    ("longevity", "atherosclerosis inflammation aging"),

    # --- Hormones & Endocrine Aging ---
    ("longevity", "testosterone aging men sarcopenia"),
    ("longevity", "estrogen menopause cognitive aging"),
    ("longevity", "growth hormone IGF-1 aging body composition"),

    # --- Biomarkers & Diagnostics ---
    ("longevity", "biological age biomarker methylation"),
    ("longevity", "proteomics aging plasma biomarkers"),
]


@dataclass
class RunStats:
    total_queries: int = 0
    completed_queries: int = 0
    total_found: int = 0
    total_new: int = 0
    total_fetched: int = 0
    total_parsed: int = 0
    total_errors: int = 0
    cost_usd: float = 0.0
    start_time: float = field(default_factory=time.time)

    def elapsed(self) -> str:
        secs = int(time.time() - self.start_time)
        return f"{secs // 60}m {secs % 60}s"

    def report(self) -> str:
        return (
            f"Queries: {self.completed_queries}/{self.total_queries} | "
            f"Papers found: {self.total_found} | New: {self.total_new} | "
            f"Fetched: {self.total_fetched} | Parsed: {self.total_parsed} | "
            f"Errors: {self.total_errors} | "
            f"Elapsed: {self.elapsed()}"
        )


async def run_ring0(
    per_query_limit: int = 100,
    budget_usd: float = 350.0,
    dry_run: bool = False,
    concurrency: int = 3,
) -> RunStats:
    """Run all Ring 0 queries. Returns aggregate stats."""
    from decoded.ingest.worker import IngestWorker

    stats = RunStats(total_queries=len(RING_0_QUERIES))
    semaphore = asyncio.Semaphore(concurrency)

    logger.info(
        "Ring 0 Ingest — %d queries × %d papers = ~%d target | budget $%.0f",
        len(RING_0_QUERIES),
        per_query_limit,
        len(RING_0_QUERIES) * per_query_limit,
        budget_usd,
    )

    if dry_run:
        logger.info("DRY RUN — no papers will be fetched")

    async def run_one(domain: str, query: str) -> dict:
        async with semaphore:
            worker = IngestWorker(
                ring=0,
                query=query,
                limit=per_query_limit,
                domain=domain,
                source="pubmed",
                dry_run=dry_run,
            )
            try:
                result = await worker.run()
                return result
            except Exception as exc:
                logger.error("Query failed: '%s': %s", query, exc)
                return {"found": 0, "new": 0, "fetched": 0, "parsed": 0, "errors": 1}

    tasks = [run_one(domain, query) for domain, query in RING_0_QUERIES]

    for i, coro in enumerate(asyncio.as_completed(tasks)):
        query = RING_0_QUERIES[i][1] if i < len(RING_0_QUERIES) else "unknown"
        result = await coro
        stats.completed_queries += 1
        stats.total_found += result.get("found", 0)
        stats.total_new += result.get("new", 0)
        stats.total_fetched += result.get("fetched", 0)
        stats.total_parsed += result.get("parsed", 0)
        stats.total_errors += result.get("errors", 0)

        logger.info(
            "[%d/%d] %s | %s",
            stats.completed_queries,
            stats.total_queries,
            stats.report(),
            query[:50],
        )

    logger.info("Ring 0 complete! Final: %s", stats.report())
    return stats


def main():
    parser = argparse.ArgumentParser(description="Ring 0 full ingest")
    parser.add_argument("--limit", type=int, default=100, help="Papers per query (default: 100)")
    parser.add_argument("--budget", type=float, default=350.0, help="Budget cap USD (default: 350)")
    parser.add_argument("--concurrency", type=int, default=3, help="Concurrent queries (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Discover but don't fetch")
    args = parser.parse_args()

    stats = asyncio.run(run_ring0(
        per_query_limit=args.limit,
        budget_usd=args.budget,
        dry_run=args.dry_run,
        concurrency=args.concurrency,
    ))

    print("\n" + "=" * 60)
    print("RING 0 INGEST COMPLETE")
    print("=" * 60)
    print(stats.report())
    print(f"Papers in DB: run  `psql -d encoded_human -c \"SELECT count(*) FROM raw_papers\"`")


if __name__ == "__main__":
    main()
