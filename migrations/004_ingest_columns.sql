-- Migration 004: Add ingest pipeline columns to raw_papers
-- Run: psql -d encoded_human -f migrations/004_ingest_columns.sql

BEGIN;

-- Add pub_year for easy year-based queries
ALTER TABLE raw_papers
    ADD COLUMN IF NOT EXISTS pub_year SMALLINT;

-- Add extracted sections as JSONB (intro/methods/results/discussion/conclusion)
ALTER TABLE raw_papers
    ADD COLUMN IF NOT EXISTS sections JSONB NOT NULL DEFAULT '{}';

-- Add reference count
ALTER TABLE raw_papers
    ADD COLUMN IF NOT EXISTS reference_count INTEGER;

-- Add references list as JSONB
ALTER TABLE raw_papers
    ADD COLUMN IF NOT EXISTS references_list JSONB NOT NULL DEFAULT '[]';

-- Expand status CHECK to include 'parsed'
-- Drop and recreate the constraint (PostgreSQL approach)
ALTER TABLE raw_papers DROP CONSTRAINT IF EXISTS raw_papers_status_check;

ALTER TABLE raw_papers
    ADD CONSTRAINT raw_papers_status_check
    CHECK (status IN (
        'queued', 'fetching', 'fetched', 'parsed',
        'extracting', 'extracted',
        'connecting', 'connected',
        'critiqued', 'error', 'skipped'
    ));

-- Index on pub_year for date-range queries
CREATE INDEX IF NOT EXISTS idx_raw_papers_pub_year
    ON raw_papers (pub_year DESC NULLS LAST);

-- Index on sections for papers that have been parsed
CREATE INDEX IF NOT EXISTS idx_raw_papers_has_sections
    ON raw_papers ((sections != '{}'))
    WHERE sections != '{}';

COMMIT;
