-- Migration 002: Extraction results with pgvector embeddings
-- Run: psql -d encoded_human -f migrations/002_extractions.sql

BEGIN;

-- Enable pgvector extension
CREATE EXTENSION IF NOT EXISTS vector;

-- Full extraction results for each paper
CREATE TABLE IF NOT EXISTS extraction_results (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id            UUID NOT NULL REFERENCES raw_papers(id) ON DELETE CASCADE,
    model_id            TEXT NOT NULL,
    study_design        TEXT NOT NULL DEFAULT 'unknown',
    sample_size         INTEGER,
    population          TEXT,
    intervention        TEXT,
    comparator          TEXT,
    primary_outcome     TEXT,
    secondary_outcomes  JSONB NOT NULL DEFAULT '[]',
    entities            JSONB NOT NULL DEFAULT '[]',
    claims              JSONB NOT NULL DEFAULT '[]',
    mechanisms          JSONB NOT NULL DEFAULT '[]',
    methods             JSONB NOT NULL DEFAULT '[]',
    key_findings        JSONB NOT NULL DEFAULT '[]',
    limitations         JSONB NOT NULL DEFAULT '[]',
    funding_sources     JSONB NOT NULL DEFAULT '[]',
    conflicts_of_interest TEXT,
    -- 1536-dim vector (OpenAI text-embedding-3-small or equivalent)
    embedding           vector(1536),
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd            NUMERIC(10, 6) NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT extraction_results_paper_model_unique UNIQUE (paper_id, model_id)
);

CREATE INDEX IF NOT EXISTS idx_extraction_results_paper_id
    ON extraction_results (paper_id);

CREATE INDEX IF NOT EXISTS idx_extraction_results_model_id
    ON extraction_results (model_id);

-- IVFFlat index for approximate nearest-neighbor search on embeddings
-- (requires at least ~1000 rows before building for good performance)
CREATE INDEX IF NOT EXISTS idx_extraction_results_embedding
    ON extraction_results USING ivfflat (embedding vector_cosine_ops)
    WITH (lists = 100);

CREATE INDEX IF NOT EXISTS idx_extraction_results_study_design
    ON extraction_results (study_design);

COMMIT;
