-- Migration 011: Data provenance and quality tracking
-- Tracks where paper data came from and how complete extractions are
-- This enables quality gates in the critique pipeline

-- 1. Track data source on raw_papers
ALTER TABLE raw_papers ADD COLUMN IF NOT EXISTS data_source VARCHAR(30) DEFAULT 'unknown';
-- Values: full_text_pmc, full_text_biorxiv, abstract_only, partial_text, unknown

-- 2. Track extraction quality metrics
ALTER TABLE extraction_results ADD COLUMN IF NOT EXISTS extraction_completeness REAL DEFAULT 0;
ALTER TABLE extraction_results ADD COLUMN IF NOT EXISTS fields_extracted INT DEFAULT 0;
ALTER TABLE extraction_results ADD COLUMN IF NOT EXISTS fields_attempted INT DEFAULT 10;
ALTER TABLE extraction_results ADD COLUMN IF NOT EXISTS was_truncated BOOLEAN DEFAULT FALSE;

-- 3. Track brief confidence on critiques
ALTER TABLE paper_critiques ADD COLUMN IF NOT EXISTS brief_confidence VARCHAR(20) DEFAULT 'unknown';
-- Values: high (full text + rich extraction), medium (partial text), low (abstract only), insufficient

-- 4. Backfill data_source based on existing data
UPDATE raw_papers
SET data_source = CASE
    WHEN full_text IS NOT NULL AND length(full_text) > 500 THEN
        CASE WHEN source = 'biorxiv' OR source = 'medrxiv' THEN 'full_text_biorxiv'
             ELSE 'full_text_pmc'
        END
    WHEN abstract IS NOT NULL AND length(abstract) > 50 THEN 'abstract_only'
    ELSE 'unknown'
END
WHERE data_source = 'unknown' OR data_source IS NULL;

-- 5. Backfill extraction_completeness from existing data
UPDATE extraction_results er
SET
    fields_extracted = (
        CASE WHEN study_design IS NOT NULL AND study_design != 'unknown' THEN 1 ELSE 0 END
        + CASE WHEN sample_size IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN population IS NOT NULL AND population != '' THEN 1 ELSE 0 END
        + CASE WHEN intervention IS NOT NULL AND intervention != '' THEN 1 ELSE 0 END
        + CASE WHEN primary_outcome IS NOT NULL AND primary_outcome != '' THEN 1 ELSE 0 END
        + CASE WHEN jsonb_array_length(COALESCE(entities::jsonb, '[]'::jsonb)) > 0 THEN 1 ELSE 0 END
        + CASE WHEN jsonb_array_length(COALESCE(claims::jsonb, '[]'::jsonb)) > 0 THEN 1 ELSE 0 END
        + CASE WHEN jsonb_array_length(COALESCE(mechanisms::jsonb, '[]'::jsonb)) > 0 THEN 1 ELSE 0 END
        + CASE WHEN jsonb_array_length(COALESCE(key_findings::jsonb, '[]'::jsonb)) > 0 THEN 1 ELSE 0 END
        + CASE WHEN jsonb_array_length(COALESCE(methods::jsonb, '[]'::jsonb)) > 0 THEN 1 ELSE 0 END
    ),
    fields_attempted = 10,
    extraction_completeness = (
        CASE WHEN study_design IS NOT NULL AND study_design != 'unknown' THEN 1 ELSE 0 END
        + CASE WHEN sample_size IS NOT NULL THEN 1 ELSE 0 END
        + CASE WHEN population IS NOT NULL AND population != '' THEN 1 ELSE 0 END
        + CASE WHEN intervention IS NOT NULL AND intervention != '' THEN 1 ELSE 0 END
        + CASE WHEN primary_outcome IS NOT NULL AND primary_outcome != '' THEN 1 ELSE 0 END
        + CASE WHEN jsonb_array_length(COALESCE(entities::jsonb, '[]'::jsonb)) > 0 THEN 1 ELSE 0 END
        + CASE WHEN jsonb_array_length(COALESCE(claims::jsonb, '[]'::jsonb)) > 0 THEN 1 ELSE 0 END
        + CASE WHEN jsonb_array_length(COALESCE(mechanisms::jsonb, '[]'::jsonb)) > 0 THEN 1 ELSE 0 END
        + CASE WHEN jsonb_array_length(COALESCE(key_findings::jsonb, '[]'::jsonb)) > 0 THEN 1 ELSE 0 END
        + CASE WHEN jsonb_array_length(COALESCE(methods::jsonb, '[]'::jsonb)) > 0 THEN 1 ELSE 0 END
    )::real / 10.0;

-- 6. Backfill brief_confidence based on paper data_source
UPDATE paper_critiques pc
SET brief_confidence = CASE
    WHEN rp.data_source LIKE 'full_text%' AND er.extraction_completeness >= 0.5 THEN 'high'
    WHEN rp.data_source LIKE 'full_text%' THEN 'medium'
    WHEN rp.data_source = 'abstract_only' THEN 'low'
    ELSE 'low'
END
FROM raw_papers rp
LEFT JOIN extraction_results er ON er.paper_id = rp.id
WHERE pc.paper_id = rp.id
  AND (pc.brief_confidence = 'unknown' OR pc.brief_confidence IS NULL);

-- 7. Index for filtering
CREATE INDEX IF NOT EXISTS idx_raw_papers_data_source ON raw_papers(data_source);
CREATE INDEX IF NOT EXISTS idx_paper_critiques_brief_confidence ON paper_critiques(brief_confidence);
CREATE INDEX IF NOT EXISTS idx_extraction_completeness ON extraction_results(extraction_completeness);
