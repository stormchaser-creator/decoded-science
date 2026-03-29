-- Migration 007: Convergence zones table
-- Materialized convergence zones with convergent claim text
-- Populated by the compute_convergence_zones job

CREATE TABLE IF NOT EXISTS convergence_zones (
    id                      UUID PRIMARY KEY DEFAULT uuid_generate_v4(),
    anchor_paper_id         UUID REFERENCES raw_papers(id) ON DELETE CASCADE,
    convergent_claim        TEXT,
    disciplines             JSONB DEFAULT '[]',
    discipline_count        INT DEFAULT 0,
    paper_ids               TEXT[] DEFAULT '{}',
    paper_count             INT DEFAULT 0,
    connection_count        INT DEFAULT 0,
    avg_confidence          FLOAT DEFAULT 0.0,
    avg_evidence_strength   FLOAT DEFAULT 0.0,
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_convergence_anchor ON convergence_zones(anchor_paper_id);
CREATE INDEX IF NOT EXISTS idx_convergence_discipline_count ON convergence_zones(discipline_count DESC);
CREATE INDEX IF NOT EXISTS idx_convergence_confidence ON convergence_zones(avg_confidence DESC);
CREATE INDEX IF NOT EXISTS idx_convergence_connection_count ON convergence_zones(connection_count DESC);
