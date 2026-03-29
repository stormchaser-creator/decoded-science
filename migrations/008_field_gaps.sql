-- Migration 008: Field gaps table
-- Structured research gaps discovered from graph negative space
-- Populated by the discover_field_gaps job

CREATE TABLE IF NOT EXISTS field_gaps (
    id                  UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    description         TEXT NOT NULL,
    discipline          VARCHAR(100),
    related_mechanisms  JSONB DEFAULT '[]',
    related_entities    JSONB DEFAULT '[]',
    adjacent_fields     JSONB DEFAULT '[]',
    importance          VARCHAR(20) DEFAULT 'medium',  -- high, medium, low
    tractability        VARCHAR(20) DEFAULT 'medium',  -- high, medium, low
    evidence_basis      TEXT,
    discovered_at       TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS idx_gaps_discipline ON field_gaps(discipline);
CREATE INDEX IF NOT EXISTS idx_gaps_importance ON field_gaps(importance);
CREATE INDEX IF NOT EXISTS idx_gaps_discovered ON field_gaps(discovered_at DESC);
