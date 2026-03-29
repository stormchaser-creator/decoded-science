-- Migration 009: Bridge results cache
-- Caches bridge query results so repeated queries are instant

CREATE TABLE IF NOT EXISTS bridge_results (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    concept_a           VARCHAR(255) NOT NULL,
    concept_b           VARCHAR(255) NOT NULL,
    path_found          BOOLEAN NOT NULL DEFAULT FALSE,
    path_type           VARCHAR(30),         -- graph_traversal, semantic_bridge, llm_hypothesis, none
    path_data           JSONB,
    hypothesis          TEXT,
    confidence          FLOAT,
    assessment          VARCHAR(50),         -- mechanistic_link, shared_pathway, structural_analogy, insufficient_evidence
    model_used          VARCHAR(50),
    cost_usd            DECIMAL(10,6) DEFAULT 0,
    query_count         INT DEFAULT 1,
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE(concept_a, concept_b)
);

CREATE INDEX IF NOT EXISTS idx_bridge_concepts ON bridge_results(concept_a, concept_b);
CREATE INDEX IF NOT EXISTS idx_bridge_created ON bridge_results(created_at DESC);
