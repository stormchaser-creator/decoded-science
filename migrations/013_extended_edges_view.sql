-- Migration 013: entity_edges_extended view
--
-- The curated `entity_edges` table has ~10K edges, seeded from a narrow
-- hand-curated canonical set. Discovery traversal and seed resolution
-- read ONLY from this table, which means the 263K+ triples already
-- extracted into `paper_claim_triples` — the actual emergent connectome
-- from the 17K+ extracted papers — are invisible to Discovery.
--
-- Symptom (2026-04-20): Eric asked Discovery "Glioblastoma multiforme
-- how does it start." Glioblastoma has 168 supporting papers in
-- discovered_entities and 75 triples in paper_claim_triples, but 0
-- rows in entity_edges. The query failed with "No seeds resolved" —
-- the substrate exists, the traversal just can't see it.
--
-- This view unions entity_edges with paper_claim_triples shaped as
-- edges. Discovery's RESOLVE_SEED_SQL and TRAVERSE_PATHS_SQL are
-- swapped to read from this view so the whole emergent substrate
-- becomes traversable.
--
-- Aggregation: multiple triples with the same (subject, predicate,
-- object) get collapsed into a single virtual edge whose support_count
-- is the number of supporting triples and whose mean_confidence is the
-- average triple confidence.

CREATE OR REPLACE VIEW entity_edges_extended AS
-- (1) Curated + backbone edges already in entity_edges
SELECT
  id::text                                          AS edge_key,
  source_entity_id,
  source_entity_name,
  target_entity_id,
  target_entity_name,
  predicate_type,
  direction,
  source_operation,
  target_operation,
  is_cross_operation,
  support_count,
  supporting_paper_ids,
  mean_confidence,
  max_confidence,
  edge_source,
  contradiction_load
FROM entity_edges

UNION ALL

-- (2) Virtual edges derived from paper_claim_triples.
--     Collapsed by (subject, predicate, object) so repeated triples
--     from multiple papers become one edge with proper support_count.
SELECT
  'triple:' || md5(lower(pct.subject) || '|' || pct.predicate || '|' || lower(pct.object))
                                                    AS edge_key,
  NULL::uuid                                        AS source_entity_id,
  pct.subject                                       AS source_entity_name,
  NULL::uuid                                        AS target_entity_id,
  pct.object                                        AS target_entity_name,
  COALESCE(pct.predicate_type, pct.predicate)       AS predicate_type,
  pct.direction                                     AS direction,
  MAX(pct.primary_operation)                        AS source_operation,
  MAX(pct.secondary_operation)                      AS target_operation,
  (MAX(pct.primary_operation) IS NOT NULL
    AND MAX(pct.secondary_operation) IS NOT NULL
    AND MAX(pct.primary_operation) <> MAX(pct.secondary_operation))
                                                    AS is_cross_operation,
  COUNT(*)::int                                     AS support_count,
  ARRAY_AGG(DISTINCT pct.paper_id) FILTER (WHERE pct.paper_id IS NOT NULL)
                                                    AS supporting_paper_ids,
  ROUND(AVG(pct.confidence)::numeric, 3)            AS mean_confidence,
  ROUND(MAX(pct.confidence)::numeric, 3)            AS max_confidence,
  'triple'::text                                    AS edge_source,
  0                                                 AS contradiction_load
FROM paper_claim_triples pct
WHERE pct.subject IS NOT NULL
  AND pct.object IS NOT NULL
  AND pct.subject <> ''
  AND pct.object  <> ''
GROUP BY
  pct.subject, pct.object, pct.predicate, pct.predicate_type, pct.direction;

COMMENT ON VIEW entity_edges_extended IS
  'Unions the curated entity_edges table (backbone + manually-validated edges) '
  'with edges derived from paper_claim_triples (263K+ extracted relations from '
  '17K+ processed papers). Discovery reads from this view so the emergent '
  'connectome is actually traversable. edge_source = ''triple'' marks virtual '
  'edges; everything else (''backbone'', ''extracted'', etc.) comes from the '
  'curated table.';

-- Helper index on paper_claim_triples to keep the view's GROUP BY fast.
-- Case-insensitive since discovery matches on lower(subject/object).
CREATE INDEX IF NOT EXISTS idx_paper_claim_triples_subject_lower
  ON paper_claim_triples (lower(subject));
CREATE INDEX IF NOT EXISTS idx_paper_claim_triples_object_lower
  ON paper_claim_triples (lower(object));
