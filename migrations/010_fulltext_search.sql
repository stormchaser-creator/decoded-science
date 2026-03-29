-- 010: Add full-text search vector to raw_papers
-- Replaces slow ILIKE '%term%' queries with GIN-indexed tsvector search

ALTER TABLE raw_papers ADD COLUMN IF NOT EXISTS search_vector tsvector;

-- Populate from title + abstract
UPDATE raw_papers
SET search_vector = to_tsvector('english', COALESCE(title, '') || ' ' || COALESCE(abstract, ''));

-- Create GIN index for fast full-text search
CREATE INDEX IF NOT EXISTS idx_raw_papers_search_vector ON raw_papers USING gin(search_vector);

-- Trigger to keep search_vector updated on insert/update
CREATE OR REPLACE FUNCTION raw_papers_search_vector_update() RETURNS trigger AS $$
BEGIN
  NEW.search_vector := to_tsvector('english', COALESCE(NEW.title, '') || ' ' || COALESCE(NEW.abstract, ''));
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_raw_papers_search_vector ON raw_papers;
CREATE TRIGGER trg_raw_papers_search_vector
  BEFORE INSERT OR UPDATE OF title, abstract ON raw_papers
  FOR EACH ROW EXECUTE FUNCTION raw_papers_search_vector_update();
