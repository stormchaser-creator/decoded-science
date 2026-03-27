-- Migration 001: Raw papers and ingest runs
-- Run: psql -d encoded_human -f migrations/001_raw_papers.sql

BEGIN;

-- Track ingest pipeline runs
CREATE TABLE IF NOT EXISTS ingest_runs (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    domain          TEXT NOT NULL DEFAULT 'longevity',
    ring            SMALLINT NOT NULL CHECK (ring IN (0, 1, 2)),
    source          TEXT NOT NULL,          -- 'pubmed', 'arxiv', 'biorxiv'
    query           TEXT NOT NULL,
    max_results     INTEGER NOT NULL DEFAULT 200,
    papers_found    INTEGER NOT NULL DEFAULT 0,
    papers_new      INTEGER NOT NULL DEFAULT 0,
    papers_skipped  INTEGER NOT NULL DEFAULT 0,
    status          TEXT NOT NULL DEFAULT 'running'
                        CHECK (status IN ('running', 'completed', 'failed')),
    error           TEXT,
    started_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    completed_at    TIMESTAMPTZ,
    cost_usd        NUMERIC(10, 6) NOT NULL DEFAULT 0
);

-- Raw papers as received from sources
CREATE TABLE IF NOT EXISTS raw_papers (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source          TEXT NOT NULL,
    external_id     TEXT NOT NULL,
    title           TEXT NOT NULL,
    abstract        TEXT,
    authors         JSONB NOT NULL DEFAULT '[]',
    journal         TEXT,
    published_date  DATE,
    doi             TEXT,
    pmc_id          TEXT,
    full_text_url   TEXT,
    full_text       TEXT,
    mesh_terms      JSONB NOT NULL DEFAULT '[]',
    keywords        JSONB NOT NULL DEFAULT '[]',
    citation_count  INTEGER,
    status          TEXT NOT NULL DEFAULT 'queued'
                        CHECK (status IN (
                            'queued', 'fetching', 'fetched',
                            'extracting', 'extracted',
                            'connecting', 'connected',
                            'critiqued', 'error', 'skipped'
                        )),
    ingest_run_id   UUID REFERENCES ingest_runs(id) ON DELETE SET NULL,
    raw_metadata    JSONB NOT NULL DEFAULT '{}',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    CONSTRAINT raw_papers_source_external_id_unique UNIQUE (source, external_id)
);

-- Indexes for common access patterns
CREATE INDEX IF NOT EXISTS idx_raw_papers_status
    ON raw_papers (status);

CREATE INDEX IF NOT EXISTS idx_raw_papers_published_date
    ON raw_papers (published_date DESC NULLS LAST);

CREATE INDEX IF NOT EXISTS idx_raw_papers_doi
    ON raw_papers (doi)
    WHERE doi IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_raw_papers_source
    ON raw_papers (source);

CREATE INDEX IF NOT EXISTS idx_raw_papers_ingest_run
    ON raw_papers (ingest_run_id)
    WHERE ingest_run_id IS NOT NULL;

CREATE INDEX IF NOT EXISTS idx_ingest_runs_domain_ring
    ON ingest_runs (domain, ring);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_updated_at_column()
RETURNS TRIGGER AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS raw_papers_updated_at ON raw_papers;
CREATE TRIGGER raw_papers_updated_at
    BEFORE UPDATE ON raw_papers
    FOR EACH ROW EXECUTE FUNCTION update_updated_at_column();

COMMIT;
