-- Migration 014: Clinical Etiology Briefs ("Why Me" mode)
--
-- New Foundry mode: `clinical_etiology`. Where paper-mode answers "is this
-- thesis defensible enough for a journal", clinical-etiology mode answers
-- "given this patient/question, integrating across ten normally-siloed
-- literatures, what is the honest contributory picture?"
--
-- Architecture:
--   1. User submits a question ("why does GBM start in an individual")
--      with optional patient_context (age, sex, history, presentation).
--   2. Fan-out orchestrator runs N parallel Discovery traversals, one per
--      etiologic frame (germline, cell-of-origin, aging, microbiome, etc.).
--   3. Structural synthesizer computes convergent nodes (concepts in ≥3
--      frames), bridge nodes (concepts spanning ≥2 siloed frames), gaps
--      (frames where substrate is thin), patient-variable factors.
--   4. Narrative synthesizer (Claude Sonnet) reads the structural data
--      and drafts a clinician-facing brief.
--
-- Tables:
--   rf_etiology_frames      — registry of etiologic lenses (germline, etc.)
--   rf_etiology_briefs      — one row per question/case
--   rf_etiology_frame_runs  — per-frame Discovery run link (brief↔frame↔run)

CREATE TABLE IF NOT EXISTS rf_etiology_frames (
  id                    TEXT PRIMARY KEY,              -- 'germline_predisposition'
  label                 TEXT NOT NULL,                 -- 'Germline predisposition'
  description           TEXT NOT NULL,                 -- what this frame answers
  frame_question        TEXT NOT NULL,                 -- "What was this patient born with?"
  default_seeds         TEXT[] NOT NULL,               -- generic seeds for this frame
  target_templates      TEXT[] NOT NULL,               -- with {condition} placeholder
  patient_variable      BOOLEAN NOT NULL DEFAULT FALSE,-- does this frame surface factors that vary person-to-person?
  stratifying_questions TEXT[],                        -- what to ask the patient for this frame
  active                BOOLEAN NOT NULL DEFAULT TRUE,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

COMMENT ON TABLE rf_etiology_frames IS
  'Library of etiologic lenses used in clinical-etiology mode. Each frame is '
  'one parallel Discovery traversal with frame-specific seeds and targets. '
  'Frames are intentionally aligned with the communities that DO NOT normally '
  'read each other (genomics vs microbiome vs chronobiology vs aging), so '
  'the synthesizer detects the cross-domain attractors nobody assembles.';

CREATE TABLE IF NOT EXISTS rf_etiology_briefs (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  question              TEXT NOT NULL,
  condition             TEXT,                          -- 'glioblastoma' (for {condition} interpolation)
  patient_context       JSONB,                         -- age, sex, presentation, relevant history
  frames_requested      TEXT[] NOT NULL,               -- which frame IDs were fanned out
  status                TEXT NOT NULL DEFAULT 'pending',
                           -- pending | fanning_out | synthesizing | complete | failed
  progress_message      TEXT,
  error                 TEXT,
  structural_synthesis  JSONB,                         -- convergent_nodes, bridge_nodes, gaps, patient_variable_factors
  brief_md              TEXT,                          -- rendered clinician-facing markdown
  total_cost_usd        DOUBLE PRECISION DEFAULT 0,
  created_at            TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at          TIMESTAMPTZ,
  CHECK (status IN ('pending','fanning_out','synthesizing','complete','failed'))
);

CREATE INDEX IF NOT EXISTS idx_rf_etiology_briefs_status
  ON rf_etiology_briefs(status, created_at DESC);
CREATE INDEX IF NOT EXISTS idx_rf_etiology_briefs_condition
  ON rf_etiology_briefs(lower(condition));

COMMENT ON TABLE rf_etiology_briefs IS
  'One row per "why me"-class question. Fan-out orchestrator creates the row, '
  'spins up N rf_etiology_frame_runs, waits for completion, then the '
  'synthesizer fills structural_synthesis + brief_md.';

CREATE TABLE IF NOT EXISTS rf_etiology_frame_runs (
  id                   UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  brief_id             UUID NOT NULL REFERENCES rf_etiology_briefs(id) ON DELETE CASCADE,
  frame_id             TEXT NOT NULL REFERENCES rf_etiology_frames(id),
  resolved_seeds       TEXT[] NOT NULL,                -- after merging default_seeds with condition-specific ones
  resolved_targets     TEXT[] NOT NULL,                -- after {condition} interpolation
  discovery_run_id     UUID REFERENCES pearl_discovery_runs(id) ON DELETE SET NULL,
  status               TEXT NOT NULL DEFAULT 'pending',
                          -- pending | running | complete | failed | empty
  paths_found          INTEGER DEFAULT 0,
  error                TEXT,
  created_at           TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at         TIMESTAMPTZ,
  CHECK (status IN ('pending','running','complete','failed','empty'))
);

CREATE INDEX IF NOT EXISTS idx_rf_etiology_frame_runs_brief
  ON rf_etiology_frame_runs(brief_id);

COMMENT ON TABLE rf_etiology_frame_runs IS
  'One row per (brief × frame). Tracks which Discovery run executed for '
  'that frame, how many paths it returned, and whether it completed. '
  'Frames with 0 paths are flagged as substrate gaps in the final brief.';

-- Seed the initial frame library for GBM proof-of-concept.
INSERT INTO rf_etiology_frames (id, label, description, frame_question, default_seeds, target_templates, patient_variable, stratifying_questions)
VALUES
  ('germline_predisposition',
   'Germline predisposition',
   'Heritable genetic variants that raise baseline risk, covered by cancer-genetics clinics but rarely integrated into initiation etiology.',
   'What was this patient born with that made them more vulnerable?',
   ARRAY['TP53','NF1','CDKN2A','TERT','POT1','MSH2','MLH1','BRCA1','BRCA2','Lynch syndrome','Li-Fraumeni','hereditary cancer'],
   ARRAY['{condition}','{condition} predisposition','{condition} risk','{condition} germline','hereditary {condition}','{condition} familial'],
   TRUE,
   ARRAY['Family history of cancer (any site) in first-degree relatives?','Multiple primaries in the patient or a sibling?','Known cancer-predisposition syndrome?','Has germline sequencing been done?']
  ),
  ('cell_of_origin',
   'Cell of origin / developmental',
   'Which precursor cell transformed, in what developmental lineage. Lives in developmental neurobiology (Cell/Neuron), almost never cross-indexed with neuro-oncology journals.',
   'Which precursor cell transformed, and when in development did it become vulnerable?',
   ARRAY['neural stem cell','subventricular zone','SVZ','oligodendrocyte precursor','OPC','Pdgfra','Nestin','Sox2','glial lineage','astrocyte progenitor','NG2 cell','neural progenitor'],
   ARRAY['{condition} initiation','{condition} formation','{condition} cell of origin','{condition} transformation'],
   FALSE,
   ARRAY['Location of tumor (helps infer cell of origin: SVZ vs white matter vs cortex)?','Age at presentation (pediatric-adult transition reshapes likely precursor)?','Methylation subtype if available?']
  ),
  ('aging_senescence',
   'Aging and senescence',
   'Age-related cellular changes — senescence, SASP, telomere attrition, stem cell exhaustion — that set a permissive stage. Lives in aging biology, rarely threaded into tumor etiology narratives.',
   'How did time itself set the stage for transformation?',
   ARRAY['cellular senescence','SASP','p16','p21','telomere attrition','stem cell exhaustion','senescent cells','senolytic','mTOR','rapamycin','aging','geroscience'],
   ARRAY['{condition}','{condition} risk','{condition} initiation','malignant transformation','tumor formation'],
   TRUE,
   ARRAY['Age at diagnosis relative to peak incidence?','Markers of biological vs chronological age if ever measured?','Chronic inflammatory conditions?','Any known senescence-load indicators?']
  )
ON CONFLICT (id) DO NOTHING;
