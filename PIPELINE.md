# Decoded Pipeline: How Extraction, Connection, and Briefs Work

*Written for evaluation and Pearl knowledge ingestion. Last updated: 2026-04-03.*

---

## Overview

Decoded is a four-stage pipeline that transforms raw scientific papers into a structured knowledge graph of biomedical findings. Each stage feeds the next:

```
RAW PAPERS → EXTRACTION → CONNECTION DISCOVERY → INTELLIGENCE BRIEFS
  (188K)       (18K done)    (graph + embeddings)    (Sonnet synthesis)
```

The database is PostgreSQL (`encoded_human`). The graph layer is Neo4j. The queue is Redis. Workers run as PM2 processes.

---

## Stage 1: Ingestion

**What it does:** Gets papers into `raw_papers` with title, abstract, authors, journal, DOI, pub date, and optionally full text.

**Sources:**
- **PMC Bulk FTP** — the primary source. NCBI publishes a 910MB CSV (`oa_file_list.csv`) indexing all 3.5M open-access papers. The pipeline cross-references 579K aging/longevity PMIDs (from PubMed keyword searches) against this list, finds ~171K with open-access full text, and downloads their tar.gz packages from `ftp.ncbi.nlm.nih.gov`. Each package is extracted for a `.nxml` JATS XML file. Failures fall back to abstract-only from PubMed's efetch API.
- **PubMed keyword search** — E-utilities API, ~60 queries covering aging hallmarks, interventions, biomarkers, model organisms, and high-connectivity molecular nodes (CRP, IL-6, mTOR, AMPK, BDNF, NF-kB, p53, telomerase)
- **bioRxiv** and **arXiv** — supplemental preprint sources

**Paper statuses:** `queued → fetched → parsed → extracted → error`

**Key data stored:** title, abstract, full_text, sections (keyed by introduction/methods/results/discussion/conclusion), mesh_terms, keywords, authors, DOI, pmc_id, pub_year, references_list

---

## Stage 2: Extraction

**Worker:** `decoded-extract` (PM2)
**Model:** Claude Haiku (`claude-haiku-4-5-20251001`) — chosen for cost efficiency at bulk scale
**Rate:** ~8,000 papers/day
**Table:** `extraction_results`

### What the prompt asks for

The extractor sends Haiku the paper content (title + abstract always; structured sections preferred over raw full text when available, with section-specific token limits: results gets 8K, methods 5K, discussion 4K, introduction 3K, conclusion 2K). It then asks for a structured XML block containing:

**Study metadata:**
- `study_design` — one of: rct, cohort, case_control, cross_sectional, meta_analysis, systematic_review, case_report, case_series, in_vitro, animal, computational, review, editorial, unknown
- `sample_size` — integer
- `population` — brief description of subjects or model organism
- `intervention` — main treatment or exposure
- `comparator` — control group
- `primary_outcome` — main endpoint measured
- `secondary_outcomes` — comma-separated list

**Key findings** — up to 3, one or two sentences each. These are the most important sentences in the paper.

**Entities** — up to 15 biological entities:
- Types: gene, protein, disease, drug, pathway, cell_type, organism, biomarker
- Each has a confidence score (0.0–1.0): 0.9+ = explicitly named, 0.7–0.89 = clearly implied, 0.5–0.69 = inferred, <0.5 = uncertain

**Claims** — up to 10 scientific assertions:
- Types: causal, associative, null, mechanistic, descriptive
- Strength: strong, moderate, weak
- Confidence 0.0–1.0: 0.9+ = stated with evidence, 0.7–0.89 = stated, 0.5–0.69 = implied, <0.5 = speculative

**Mechanisms** — up to 5 biological pathways:
- Each has: description (text), upstream entity, downstream entity, interaction type (activates / inhibits / binds / regulates / phosphorylates / cleaves / other), confidence

**Methods** — up to 8 techniques, categorized as: sequencing, imaging, assay, computational, clinical, behavioral, other

**Limitations** — up to 5, from the paper itself or implied

**Funding and conflicts of interest**

### How it parses

The model outputs raw XML. The extractor strips XML comments (Haiku sometimes leaves placeholder comments in), parses with Python's ElementTree, and converts to typed Python objects (`ExtractionResult`, `ExtractedEntity`, `ExtractedClaim`, `ExtractedMechanism`, `ExtractedMethod`). If parsing fails because the response was truncated (stop_reason = max_tokens), it retries once at 8192 tokens. Results are written to `extraction_results` and the paper's status advances to `extracted`.

### What is NOT done in extraction

Extraction is intentionally narrow — no inference, no synthesis, only what's explicitly in the paper. The prompt says: *"Only include information explicitly stated in the paper — do not infer or speculate."* Cross-paper insight is deferred entirely to Stage 4 (briefs).

---

## Stage 3: Connection Discovery

**Worker:** `decoded-connect` (PM2)
**Purpose:** Find which extracted papers are scientifically related and classify how
**Output table:** `paper_connections`

Connection discovery runs in three sequential phases:

### Phase 1: Graph Discovery (Neo4j)

After extraction, papers and their extracted elements are written into Neo4j as nodes:
- `Paper` nodes (with title, abstract, study_design, pub_year)
- `Entity` nodes linked via `HAS_ENTITY`
- `Claim` nodes linked via `MAKES_CLAIM`
- `Mechanism` nodes linked via `DESCRIBES_MECHANISM`
- `Method` nodes linked via `USES_METHOD`

The graph discovery worker then runs four Cypher queries to find candidate pairs:

1. **Shared entities** — papers sharing ≥2 Entity nodes. *"These two papers both study mTOR and rapamycin."* Returns up to 500 pairs, ordered by shared entity count.

2. **Convergent claims** — papers making claims of the same type (causal, mechanistic, etc.) involving overlapping entities. *"Both papers make causal claims about the same pathway."* Returns up to 300 pairs. Excludes purely descriptive claims.

3. **Shared mechanisms** — papers describing mechanisms with matching upstream entities, downstream entities, or interaction types (case-insensitive string match). *"Both papers describe something inhibiting mTOR."* Returns up to 300 pairs.

4. **Methodological parallels** — papers using ≥2 of the same methods. *"Both use RNA-seq and CRISPR."* Returns up to 200 pairs.

Pairs found by multiple methods are merged (highest shared count wins, methods are concatenated).

### Phase 2: Embedding Similarity (pgvector + OpenAI)

For each extracted paper, the connect worker generates a text embedding using OpenAI `text-embedding-3-small` (1536 dimensions). The embedding input combines: title, first 600 chars of abstract, up to 3 key findings, up to 10 entity names.

Embeddings are stored in `extraction_results.embedding` as a pgvector column. The worker then runs a single SQL query finding all pairs with cosine similarity ≥ 0.75, up to 500 pairs per run. This catches thematic connections that share no explicit entity names — e.g., two papers studying the same phenomenon in different organisms with different terminology.

### Phase 3: LLM Validation (Sonnet)

Every candidate pair from Phases 1 and 2 is validated by Claude Sonnet (`claude-sonnet-4-6`). This is the quality gate. The prompt gives Sonnet:
- Title, abstract (first 400 chars), and up to 3 key findings for each paper
- The shared entities or similarity score that triggered the candidate
- The discovery method

Sonnet responds with JSON:
```json
{
  "connected": true,
  "connection_type": "extends|contradicts|mechanism_for|shares_target|methodological_parallel|convergent_evidence",
  "description": "One sentence describing the connection",
  "confidence": 0.0–1.0,
  "novelty_score": 0.0–1.0,
  "supporting_evidence": ["point 1", "point 2"]
}
```

If `connected` is false, the pair is discarded. If the connection type is `replicates`, it's also discarded (replication isn't interesting for discovery). Only pairs where Sonnet confirms a real connection are written to `paper_connections`.

**Connection types defined:**
- `extends` — B builds on or expands A's findings
- `contradicts` — B's results conflict with A's
- `mechanism_for` — B provides the mechanistic explanation for A's observation
- `shares_target` — different interventions, same biological target
- `methodological_parallel` — same technique applied to different questions
- `convergent_evidence` — independent lines of evidence arriving at same conclusion

### On-demand: Bridge Hypothesis

The `/bridge` API endpoint is a separate flow. Given two concept strings (e.g., "rapamycin" and "gut microbiome"), it:
1. Fetches papers related to each concept from the DB
2. Runs a Neo4j shortest-path query up to 4 hops between concept-matching nodes
3. Runs pgvector to find semantically bridging papers
4. Sends all of this to Sonnet with a structured prompt

Sonnet returns a formatted bridge hypothesis with: stated connection, mechanistic pathway (step by step), supporting evidence (citing specific papers/findings), evidence strength rating, and a suggested experiment.

---

## Stage 4: Intelligence Briefs

**Worker:** `decoded-critique` (PM2)
**Model:** Claude Sonnet (`claude-sonnet-4-6`) — Haiku is explicitly not used here; synthesis requires stronger reasoning
**Table:** `paper_critiques`

### The core design principle

The system prompt is unambiguous: *"Your role is NOT to summarize papers — researchers can read abstracts themselves. Your role is to produce Intelligence Briefs that surface NEW INSIGHTS that only emerge from analyzing this paper alongside its connections to other papers in the corpus."*

The summary field in a brief must answer: *"What do I learn from this paper that I couldn't learn by reading it alone?"*

### Data quality gate

Before generating a brief, the generator assesses what data is actually available:
- Does it have full text or just abstract?
- Is study design, population, and primary outcome populated?
- Are there ≥2 key findings?
- Are there ≥3 entities and ≥2 claims?

This produces a data quality level: `high`, `medium`, or `low`. The level is passed into the prompt explicitly, with instructions to cap methodology and statistical rigor scores at 5.0 if the methods section isn't visible. This prevents the model from hallucinating confident scores from thin data.

Papers with fewer than 2 entities AND fewer than 1 claim AND no abstract are skipped entirely.

### What the brief prompt contains

- Paper metadata: title, authors, journal, date, DOI, study design, population, primary outcome
- Abstract (full)
- Key findings extracted in Stage 2
- Up to 10 known connections from Stage 3, formatted as: `CONNECTION_TYPE → Paper Title: one-sentence description`
- The data completeness context block
- The instruction to focus on corpus-level insight

### What it produces

```json
{
  "overall_quality": "high|medium|low",
  "methodology_score": 0.0–10.0,
  "reproducibility_score": 0.0–10.0,
  "novelty_score": 0.0–10.0,
  "statistical_rigor": 0.0–10.0,
  "strengths": ["..."],
  "weaknesses": ["..."],
  "red_flags": ["ONLY genuine methodological red flags"],
  "summary": "2-3 sentences: what this paper means IN CONTEXT of connected papers",
  "recommendation": "read|skim|skip|replicate|build_on"
}
```

**Score definitions:**
- `methodology_score` — rigor of study design, controls, sample size (capped at 5.0 if methods not visible)
- `reproducibility_score` — clarity of methods, data availability, code sharing
- `novelty_score` — how new the findings are **relative to connected papers in this corpus** (not novelty in general)
- `statistical_rigor` — appropriate tests, effect sizes, confidence intervals (capped at 5.0 without visible stats)

**Strengths** should describe what the paper **adds to the corpus**, not generic virtues like "large sample size."
**Weaknesses** should highlight where the paper **conflicts with or fails to address gaps visible from connected papers.**
**Red flags** are reserved for genuine methodological concerns — not extraction artifacts or missing metadata.

---

## Key Design Decisions

**Why Haiku for extraction, Sonnet for everything else?**
Extraction is a narrow pattern-matching task with a rigid schema — Haiku does it well at ~1/20th the cost of Sonnet. Connection validation and brief generation require genuine reasoning about relationships and synthesis across papers; Sonnet is used there.

**Why XML for extraction output, JSON for connection/critique?**
XML allows reliable parsing even when the model adds comments or slight formatting variations. The extraction schema has nested repeating elements (multiple entities, claims, mechanisms) that XML handles cleanly. JSON is used for the simpler, flatter outputs in Stages 3 and 4.

**Why does novelty_score mean "relative to this corpus" not "in general"?**
A paper published in 2010 might be foundational and novel in general, but if 40 papers in the corpus already cite and extend it, its novelty score for a user exploring this corpus should reflect that — they've already seen the downstream work.

**Why does the brief system prompt explicitly forbid summarizing?**
thedecodedhuman.com surfaces these briefs as the primary user-facing output. Summaries are redundant — the abstract is already there. The value is the corpus-level synthesis: "This paper + these 8 connected papers suggests X, which contradicts what paper Y found."

---

## Current State (2026-04-03)

| Stage | Count |
|---|---|
| Papers ingested | 188,878 |
| Papers extracted | 18,815 |
| Papers parsed (awaiting extraction) | 66,361 |
| Papers fetched (not yet parsed) | 103,680 |
| Extraction rate | ~8,000/day |
| Estimated completion | ~3 weeks |

The pipeline is running continuously. The PMC bulk download is still completing (papers with open-access full text being fetched from NCBI FTP). Extraction workers process `parsed` papers in order. Connection discovery and brief generation run on the extracted pool.

---

## What Is Not Yet Built

- **Pearl bridge** — 27 Altini papers in `raw_papers` need bridging to Pearl's `kb_entries`. The bridge module exists at `decoded/pearl/bridge.py` but the flow isn't wired into the PM2 workers.
- **Embedding coverage** — pgvector similarity requires an OpenAI API key for embedding generation. If `OPENAI_API_KEY` is not set, Phase 2 of connection discovery is silently skipped.
- **Full-text gap** — ~67% of papers are abstract-only (FTP downloads hit NCBI rate limits at high concurrency). Re-runs at lower concurrency (3 workers) are recovering these.
