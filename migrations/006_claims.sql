-- Migration 006: Claims table
-- Extracts claims from extraction_results JSONB into a queryable table
-- Run: psql -U whit -d encoded_human -f migrations/006_claims.sql

CREATE TABLE IF NOT EXISTS claims (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    paper_id            UUID REFERENCES raw_papers(id) ON DELETE CASCADE,
    text                TEXT NOT NULL,
    claim_type          VARCHAR(30),        -- finding, hypothesis, conclusion, negative_result, methodological
    evidence_strength   VARCHAR(20),        -- strong, moderate, weak, preliminary
    source_section      VARCHAR(30),        -- results, discussion, conclusion, abstract
    supporting_data     TEXT,
    confidence          FLOAT DEFAULT 0.0,
    created_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_claims_paper ON claims(paper_id);
CREATE INDEX IF NOT EXISTS idx_claims_type ON claims(claim_type);
CREATE INDEX IF NOT EXISTS idx_claims_strength ON claims(evidence_strength);

-- Migrate existing claims from extraction_results JSONB
INSERT INTO claims (paper_id, text, claim_type, evidence_strength, source_section, supporting_data, confidence)
SELECT
    er.paper_id,
    COALESCE(c->>'text', c->>'claim', '') as text,
    c->>'claim_type' as claim_type,
    c->>'evidence_strength' as evidence_strength,
    c->>'source_section' as source_section,
    c->>'supporting_data' as supporting_data,
    COALESCE((c->>'confidence')::float, 0.0) as confidence
FROM extraction_results er,
     jsonb_array_elements(
         CASE
             WHEN er.claims IS NULL THEN '[]'::jsonb
             WHEN er.claims = 'null' THEN '[]'::jsonb
             WHEN er.claims::text NOT LIKE '[%' THEN '[]'::jsonb
             ELSE er.claims::jsonb
         END
     ) AS c
WHERE COALESCE(c->>'text', c->>'claim', '') != ''
ON CONFLICT DO NOTHING;

-- Add vector embedding column if pgvector is available
-- ALTER TABLE claims ADD COLUMN IF NOT EXISTS embedding vector(1536);
-- CREATE INDEX IF NOT EXISTS idx_claims_embedding ON claims USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
