-- Migration 003: Discovered connections between papers
-- Run: psql -d encoded_human -f migrations/003_connections.sql

BEGIN;

CREATE TABLE IF NOT EXISTS discovered_connections (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_a_id          UUID NOT NULL REFERENCES raw_papers(id) ON DELETE CASCADE,
    paper_b_id          UUID NOT NULL REFERENCES raw_papers(id) ON DELETE CASCADE,
    connection_type     TEXT NOT NULL,
    -- e.g. 'replicates', 'contradicts', 'extends', 'mechanism_for',
    --      'shares_target', 'refines', 'inspired_by', 'meta_analysis_of'
    description         TEXT NOT NULL,
    confidence          NUMERIC(4, 3) NOT NULL CHECK (confidence BETWEEN 0 AND 1),
    supporting_evidence JSONB NOT NULL DEFAULT '[]',
    shared_entities     JSONB NOT NULL DEFAULT '[]',
    novelty_score       NUMERIC(4, 3) NOT NULL DEFAULT 0.5
                            CHECK (novelty_score BETWEEN 0 AND 1),
    model_id            TEXT NOT NULL,
    prompt_tokens       INTEGER NOT NULL DEFAULT 0,
    completion_tokens   INTEGER NOT NULL DEFAULT 0,
    cost_usd            NUMERIC(10, 6) NOT NULL DEFAULT 0,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Canonical ordering: always store paper_a_id < paper_b_id by UUID string
    -- to avoid duplicate (A→B) and (B→A) rows for undirected connections.
    -- Directed connection types (e.g. 'mechanism_for') preserve A→B direction.
    CONSTRAINT discovered_connections_unique
        UNIQUE (paper_a_id, paper_b_id, connection_type)
);

CREATE INDEX IF NOT EXISTS idx_connections_paper_a
    ON discovered_connections (paper_a_id);

CREATE INDEX IF NOT EXISTS idx_connections_paper_b
    ON discovered_connections (paper_b_id);

CREATE INDEX IF NOT EXISTS idx_connections_type
    ON discovered_connections (connection_type);

CREATE INDEX IF NOT EXISTS idx_connections_confidence
    ON discovered_connections (confidence DESC);

CREATE INDEX IF NOT EXISTS idx_connections_novelty
    ON discovered_connections (novelty_score DESC);

-- Composite for finding all connections involving a paper
CREATE INDEX IF NOT EXISTS idx_connections_either_paper
    ON discovered_connections (paper_a_id, paper_b_id);

-- Paper critiques
CREATE TABLE IF NOT EXISTS paper_critiques (
    id                      UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id                UUID NOT NULL REFERENCES raw_papers(id) ON DELETE CASCADE,
    model_id                TEXT NOT NULL,
    overall_quality         TEXT NOT NULL CHECK (overall_quality IN ('high', 'medium', 'low')),
    methodology_score       NUMERIC(4, 1) NOT NULL CHECK (methodology_score BETWEEN 0 AND 10),
    reproducibility_score   NUMERIC(4, 1) NOT NULL CHECK (reproducibility_score BETWEEN 0 AND 10),
    novelty_score           NUMERIC(4, 1) NOT NULL CHECK (novelty_score BETWEEN 0 AND 10),
    statistical_rigor       NUMERIC(4, 1) NOT NULL CHECK (statistical_rigor BETWEEN 0 AND 10),
    strengths               JSONB NOT NULL DEFAULT '[]',
    weaknesses              JSONB NOT NULL DEFAULT '[]',
    red_flags               JSONB NOT NULL DEFAULT '[]',
    summary                 TEXT NOT NULL,
    recommendation          TEXT NOT NULL
                                CHECK (recommendation IN ('read', 'skim', 'skip', 'replicate', 'build_on')),
    prompt_tokens           INTEGER NOT NULL DEFAULT 0,
    completion_tokens       INTEGER NOT NULL DEFAULT 0,
    cost_usd                NUMERIC(10, 6) NOT NULL DEFAULT 0,
    created_at              TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT paper_critiques_paper_model_unique UNIQUE (paper_id, model_id)
);

CREATE INDEX IF NOT EXISTS idx_critiques_paper_id
    ON paper_critiques (paper_id);

CREATE INDEX IF NOT EXISTS idx_critiques_quality
    ON paper_critiques (overall_quality);

CREATE INDEX IF NOT EXISTS idx_critiques_recommendation
    ON paper_critiques (recommendation);

COMMIT;
