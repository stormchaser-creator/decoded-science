"""Shared Pydantic models for the Decoded pipeline."""

from __future__ import annotations

import enum
from datetime import datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class PaperStatus(str, enum.Enum):
    """Lifecycle state of a paper through the pipeline."""

    QUEUED = "queued"
    FETCHING = "fetching"
    FETCHED = "fetched"
    PARSED = "parsed"
    EXTRACTING = "extracting"
    EXTRACTED = "extracted"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    CRITIQUED = "critiqued"
    ERROR = "error"
    SKIPPED = "skipped"


class StudyDesign(str, enum.Enum):
    """Classification of study methodology."""

    RCT = "rct"
    COHORT = "cohort"
    CASE_CONTROL = "case_control"
    CROSS_SECTIONAL = "cross_sectional"
    META_ANALYSIS = "meta_analysis"
    SYSTEMATIC_REVIEW = "systematic_review"
    CASE_REPORT = "case_report"
    CASE_SERIES = "case_series"
    IN_VITRO = "in_vitro"
    ANIMAL = "animal"
    COMPUTATIONAL = "computational"
    REVIEW = "review"
    EDITORIAL = "editorial"
    UNKNOWN = "unknown"


# ---------------------------------------------------------------------------
# Core paper model
# ---------------------------------------------------------------------------


class RawPaper(BaseModel):
    """Raw paper record as ingested from a source (PubMed, arXiv, etc.)."""

    id: UUID = Field(default_factory=uuid4)
    source: str  # e.g. "pubmed", "arxiv", "biorxiv"
    external_id: str  # PMID, arXiv ID, DOI, etc.
    title: str
    abstract: str | None = None
    authors: list[str] = Field(default_factory=list)
    journal: str | None = None
    published_date: datetime | None = None
    doi: str | None = None
    pmc_id: str | None = None
    full_text_url: str | None = None
    full_text: str | None = None
    mesh_terms: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    citation_count: int | None = None
    status: PaperStatus = PaperStatus.QUEUED
    ingest_run_id: UUID | None = None
    raw_metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"use_enum_values": True}


# ---------------------------------------------------------------------------
# Extraction sub-models
# ---------------------------------------------------------------------------


class ExtractedEntity(BaseModel):
    """A named entity extracted from a paper."""

    text: str
    entity_type: str  # e.g. "gene", "protein", "disease", "drug", "pathway"
    normalized_id: str | None = None  # e.g. UMLS CUI, UniProt ID
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    spans: list[tuple[int, int]] = Field(default_factory=list)  # char offsets


class ExtractedClaim(BaseModel):
    """A scientific claim extracted from a paper."""

    text: str
    claim_type: str  # e.g. "causal", "associative", "null", "mechanistic"
    subject: str | None = None
    predicate: str | None = None
    object: str | None = None
    evidence_strength: str | None = None  # "strong", "moderate", "weak"
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)
    section: str | None = None  # "abstract", "results", "discussion"


class ExtractedMechanism(BaseModel):
    """A biological or chemical mechanism described in a paper."""

    description: str
    pathway: str | None = None
    upstream_entity: str | None = None
    downstream_entity: str | None = None
    interaction_type: str | None = None  # "activates", "inhibits", "binds", etc.
    context: str | None = None  # cell type, tissue, condition
    confidence: float = Field(ge=0.0, le=1.0, default=1.0)


class ExtractedMethod(BaseModel):
    """An experimental or analytical method used in a paper."""

    name: str
    category: str | None = None  # "sequencing", "imaging", "assay", etc.
    description: str | None = None
    software: list[str] = Field(default_factory=list)
    parameters: dict[str, Any] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Aggregate extraction result
# ---------------------------------------------------------------------------


class ExtractionResult(BaseModel):
    """Full extraction output for a single paper."""

    id: UUID = Field(default_factory=uuid4)
    paper_id: UUID
    model_id: str  # e.g. "claude-opus-4-6", "claude-sonnet-4-6"
    study_design: StudyDesign = StudyDesign.UNKNOWN
    sample_size: int | None = None
    population: str | None = None
    intervention: str | None = None
    comparator: str | None = None
    primary_outcome: str | None = None
    secondary_outcomes: list[str] = Field(default_factory=list)
    entities: list[ExtractedEntity] = Field(default_factory=list)
    claims: list[ExtractedClaim] = Field(default_factory=list)
    mechanisms: list[ExtractedMechanism] = Field(default_factory=list)
    methods: list[ExtractedMethod] = Field(default_factory=list)
    key_findings: list[str] = Field(default_factory=list)
    limitations: list[str] = Field(default_factory=list)
    funding_sources: list[str] = Field(default_factory=list)
    conflicts_of_interest: str | None = None
    embedding: list[float] | None = None  # vector for similarity search
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {"use_enum_values": True}


# ---------------------------------------------------------------------------
# Connection discovery
# ---------------------------------------------------------------------------


class DiscoveredConnection(BaseModel):
    """A connection discovered between two papers by the LLM."""

    id: UUID = Field(default_factory=uuid4)
    paper_a_id: UUID
    paper_b_id: UUID
    connection_type: str  # e.g. "replicates", "contradicts", "extends", "mechanism_for"
    description: str
    confidence: float = Field(ge=0.0, le=1.0)
    supporting_evidence: list[str] = Field(default_factory=list)
    shared_entities: list[str] = Field(default_factory=list)
    novelty_score: float = Field(ge=0.0, le=1.0, default=0.5)
    model_id: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Critique
# ---------------------------------------------------------------------------


class PaperCritique(BaseModel):
    """LLM critique of a paper's methodology and claims."""

    id: UUID = Field(default_factory=uuid4)
    paper_id: UUID
    model_id: str
    overall_quality: str  # "high", "medium", "low"
    methodology_score: float = Field(ge=0.0, le=10.0)
    reproducibility_score: float = Field(ge=0.0, le=10.0)
    novelty_score: float = Field(ge=0.0, le=10.0)
    statistical_rigor: float = Field(ge=0.0, le=10.0)
    strengths: list[str] = Field(default_factory=list)
    weaknesses: list[str] = Field(default_factory=list)
    red_flags: list[str] = Field(default_factory=list)
    summary: str
    recommendation: str  # "read", "skim", "skip", "replicate", "build_on"
    prompt_tokens: int = 0
    completion_tokens: int = 0
    cost_usd: float = 0.0
    created_at: datetime = Field(default_factory=datetime.utcnow)
