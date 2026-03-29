"""Seed domain configuration: Ring 0/1/2 queries and budget limits.

Ring model:
  Ring 0 — Core focus area (highest priority, deepest extraction)
  Ring 1 — Direct adjacencies (medium priority)
  Ring 2 — Broader context (lower priority, shallow extraction)
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class RingQuery:
    """A seed query with associated metadata."""
    query: str
    source: str = "pubmed"          # "pubmed", "arxiv", "biorxiv", "semanticscholar"
    max_results: int = 200
    date_from: str | None = None    # ISO date string, e.g. "2015-01-01"
    date_to: str | None = None
    priority: int = 0               # higher = processed first


@dataclass
class BudgetConfig:
    """Daily and total spend limits per ring."""
    daily_usd: float
    total_usd: float
    max_papers_per_day: int = 500


@dataclass
class SeedDomainConfig:
    """Full seed configuration for a research domain."""
    name: str
    description: str
    ring0: list[RingQuery] = field(default_factory=list)
    ring1: list[RingQuery] = field(default_factory=list)
    ring2: list[RingQuery] = field(default_factory=list)
    budget_ring0: BudgetConfig = field(default_factory=lambda: BudgetConfig(20.0, 200.0, 200))
    budget_ring1: BudgetConfig = field(default_factory=lambda: BudgetConfig(15.0, 150.0, 300))
    budget_ring2: BudgetConfig = field(default_factory=lambda: BudgetConfig(10.0, 100.0, 500))
    total_daily_budget_usd: float = 50.0
    total_budget_usd: float = 500.0

    def all_queries(self) -> list[tuple[int, RingQuery]]:
        """Return all queries as (ring, query) sorted by priority."""
        pairs = (
            [(0, q) for q in self.ring0] +
            [(1, q) for q in self.ring1] +
            [(2, q) for q in self.ring2]
        )
        return sorted(pairs, key=lambda x: (-x[0] == 0, -x[1].priority))


# ---------------------------------------------------------------------------
# Default seed domain: Longevity / Aging Biology
# This is the initial focus for the Decoded pipeline.
# ---------------------------------------------------------------------------

LONGEVITY_DOMAIN = SeedDomainConfig(
    name="longevity",
    description="Aging biology, lifespan extension, and healthspan interventions",

    # -----------------------------------------------------------------------
    # Ring 0 — Core longevity mechanisms (deep extraction, full critique)
    # -----------------------------------------------------------------------
    ring0=[
        RingQuery(
            query="hallmarks of aging mechanisms review",
            max_results=500,
            priority=100,
        ),
        RingQuery(
            query="senescent cells clearance lifespan extension",
            max_results=300,
            priority=95,
        ),
        RingQuery(
            query="NAD+ metabolism aging sirtuin",
            max_results=300,
            priority=95,
        ),
        RingQuery(
            query="mTOR rapamycin aging longevity",
            max_results=300,
            priority=90,
        ),
        RingQuery(
            query="telomere length aging telomerase",
            max_results=300,
            priority=90,
        ),
        RingQuery(
            query="mitochondrial dysfunction aging ROS",
            max_results=300,
            priority=90,
        ),
        RingQuery(
            query="proteostasis unfolded protein response aging",
            max_results=200,
            priority=85,
        ),
        RingQuery(
            query="epigenetic clock biological age methylation",
            max_results=200,
            priority=85,
        ),
        RingQuery(
            query="caloric restriction intermittent fasting lifespan",
            max_results=300,
            priority=85,
        ),
        RingQuery(
            query="IGF-1 insulin signaling longevity pathway",
            max_results=200,
            priority=80,
        ),
        RingQuery(
            query="autophagy aging healthspan",
            max_results=200,
            priority=80,
        ),
        RingQuery(
            query="inflammaging chronic inflammation aging",
            max_results=200,
            priority=80,
        ),
        RingQuery(
            query="stem cell exhaustion aging regeneration",
            max_results=200,
            priority=75,
        ),
        RingQuery(
            query="parabiosis young blood plasma aging",
            max_results=150,
            priority=75,
        ),
        RingQuery(
            query="FOXO transcription factor longevity C elegans",
            max_results=150,
            priority=70,
        ),
        # bioRxiv preprints — cutting-edge longevity research
        RingQuery(
            query="hallmarks aging senescence telomere mitochondria epigenetic",
            source="biorxiv",
            max_results=200,
            priority=95,
        ),
        RingQuery(
            query="mTOR rapamycin NAD sirtuin aging lifespan extension",
            source="biorxiv",
            max_results=200,
            priority=90,
        ),
        RingQuery(
            query="partial reprogramming Yamanaka aging rejuvenation epigenetic reset",
            source="biorxiv",
            max_results=150,
            priority=85,
        ),
        RingQuery(
            query="senolytic senolytics senescent cell clearance aging",
            source="biorxiv",
            max_results=150,
            priority=85,
        ),
        # arXiv — computational/systems biology longevity
        RingQuery(
            query="aging longevity computational biology machine learning biomarker",
            source="arxiv",
            max_results=100,
            priority=70,
        ),
    ],

    # -----------------------------------------------------------------------
    # Ring 1 — Adjacent longevity interventions and biomarkers
    # -----------------------------------------------------------------------
    ring1=[
        RingQuery(
            query="metformin aging clinical trial TAME",
            max_results=200,
            priority=70,
        ),
        RingQuery(
            query="senolytics dasatinib quercetin aging",
            max_results=200,
            priority=70,
        ),
        RingQuery(
            query="resveratrol NMN NR supplementation aging human",
            max_results=200,
            priority=65,
        ),
        RingQuery(
            query="gut microbiome aging longevity",
            max_results=200,
            priority=65,
        ),
        RingQuery(
            query="GDF11 GDF15 aging rejuvenation",
            max_results=150,
            priority=60,
        ),
        RingQuery(
            query="biological age clock reversal reprogramming",
            max_results=200,
            priority=60,
        ),
        RingQuery(
            query="partial reprogramming Yamanaka factors aging",
            max_results=150,
            priority=60,
        ),
        RingQuery(
            query="longevity genetics centenarians GWAS",
            max_results=200,
            priority=55,
        ),
        RingQuery(
            query="exercise physical activity aging biomarkers",
            max_results=200,
            priority=55,
        ),
        RingQuery(
            query="sleep quality aging cognitive decline",
            max_results=150,
            priority=50,
        ),
        RingQuery(
            query="spermidine polyamine aging autophagy",
            max_results=150,
            priority=50,
        ),
        RingQuery(
            query="AMPK activators aging metabolism",
            max_results=150,
            priority=50,
        ),
        # bioRxiv preprints — longevity interventions
        RingQuery(
            query="metformin senolytics rapamycin longevity intervention clinical",
            source="biorxiv",
            max_results=150,
            priority=65,
        ),
        RingQuery(
            query="gut microbiome aging longevity fecal transplant",
            source="biorxiv",
            max_results=150,
            priority=60,
        ),
        RingQuery(
            query="biological age clock reversal epigenetic reprogramming",
            source="biorxiv",
            max_results=150,
            priority=60,
        ),
    ],

    # -----------------------------------------------------------------------
    # Ring 2 — Broader context: age-related diseases and systems
    # -----------------------------------------------------------------------
    ring2=[
        RingQuery(
            query="Alzheimer's disease aging neurodegeneration",
            max_results=200,
            priority=45,
        ),
        RingQuery(
            query="cardiovascular disease aging endothelial",
            max_results=200,
            priority=45,
        ),
        RingQuery(
            query="cancer aging tumor suppression",
            max_results=150,
            priority=40,
        ),
        RingQuery(
            query="type 2 diabetes insulin resistance aging",
            max_results=150,
            priority=40,
        ),
        RingQuery(
            query="sarcopenia muscle loss aging",
            max_results=150,
            priority=40,
        ),
        RingQuery(
            query="bone density osteoporosis aging",
            max_results=100,
            priority=35,
        ),
        RingQuery(
            query="immune senescence thymus aging",
            max_results=150,
            priority=35,
        ),
        RingQuery(
            query="Caenorhabditis elegans lifespan genetics",
            max_results=200,
            priority=35,
        ),
        RingQuery(
            query="Drosophila aging model lifespan",
            max_results=150,
            priority=30,
        ),
        RingQuery(
            query="mouse aging model intervention ITP",
            max_results=200,
            priority=30,
        ),
        RingQuery(
            query="naked mole rat longevity cancer resistance",
            max_results=100,
            priority=25,
        ),
    ],

    # Budget: Ring 0 gets the most resources
    budget_ring0=BudgetConfig(daily_usd=25.0, total_usd=250.0, max_papers_per_day=200),
    budget_ring1=BudgetConfig(daily_usd=15.0, total_usd=150.0, max_papers_per_day=300),
    budget_ring2=BudgetConfig(daily_usd=10.0, total_usd=100.0, max_papers_per_day=500),
    total_daily_budget_usd=50.0,
    total_budget_usd=500.0,
)


# Registry of available domains
DOMAINS: dict[str, SeedDomainConfig] = {
    "longevity": LONGEVITY_DOMAIN,
}


def get_domain(name: str = "longevity") -> SeedDomainConfig:
    if name not in DOMAINS:
        raise ValueError(f"Unknown domain '{name}'. Available: {list(DOMAINS)}")
    return DOMAINS[name]
