# Decoded

**Literature connectome — AI-discovered connections in scientific research.**

Decoded ingests scientific papers, extracts structured knowledge with LLMs, builds a Neo4j knowledge graph, discovers non-obvious connections between papers, generates Intelligence Briefs, and surfaces researchers whose work converges.

---

## Architecture

```
PMC / PubMed / arXiv
        │
        ▼
   D2: INGEST ──── fetch, parse JATS/BioC XML ──── Postgres (raw_papers)
        │
        ▼
   D3: EXTRACT ─── Claude Haiku structured analysis ─── extraction_results
        │
        ▼
   D4: GRAPH ───── Neo4j knowledge graph ──────────── Paper/Entity/Claim/
        │          (878 nodes, 846 edges)              Mechanism/Method nodes
        │
        ▼
   D5: CONNECT ─── 3-phase discovery ──────────────── discovered_connections
        │          Graph → Embedding → LLM
        │          + On-demand BRIDGE QUERY
        │
        ▼
   D6: CRITIQUE ── Intelligence Briefs ────────────── paper_critiques
        │          (Claude Sonnet)
        │
        ▼
   D7: API ──────── FastAPI REST ───────────────────── 14 endpoints
        │
        ▼
   D8: OUTREACH ─── Author email system ───────────── SQLite queue
```

---

## Sprints

| Sprint | Component | Status |
|--------|-----------|--------|
| D1 | Foundation — models, schemas, queue, config | ✅ |
| D2 | Ingest — PMC discovery, JATS/BioC parsing, 100 papers | ✅ |
| D3 | Extract — Claude Haiku structured paper analysis | ✅ |
| D4 | Graph — Neo4j knowledge graph builder | ✅ |
| D5 | Connect — 3-phase connection discovery + bridge query | ✅ |
| D6 | Critique — Intelligence Brief generation | ✅ |
| D7 | API — FastAPI with 14 endpoints | ✅ |
| D8 | Outreach — Author email system | ✅ |

---

## Quick Start

### Prerequisites

- Python 3.11+
- PostgreSQL (database: `encoded_human`) with pgvector extension
- Neo4j 5.x running on `bolt://localhost:7687`
- Redis (for job queue)

### Install

```bash
pip install -e ".[dev]"
cp .env.example .env  # add ANTHROPIC_API_KEY
```

### Run the full pipeline

```bash
# 1. Ingest papers from PubMed
python -m decoded.ingest.worker --domain longevity --ring 0 --max-results 100

# 2. Extract structured data with Claude Haiku
python -m decoded.extract.worker --limit 100

# 3. Build Neo4j knowledge graph
python -m decoded.graph.worker --limit 200

# 4. Discover connections
python -m decoded.connect.worker --phase graph,llm --limit 50

# 5. Generate Intelligence Briefs
python -m decoded.critique.worker --limit 10

# 6. Start API server
python -m decoded.api.main

# 7. Generate author outreach emails (dry run)
python -m decoded.outreach.worker --generate 5 --dry-run
```

---

## Pipeline Components

### D2: Ingest (`decoded/ingest/`)

Discovers and fetches papers from PubMed Central via E-utilities API.

```bash
python -m decoded.ingest.worker --domain longevity --ring 0 --max-results 100
```

Parses JATS XML and BioC format into structured sections (intro/methods/results/discussion).

### D3: Extract (`decoded/extract/`)

Runs Claude Haiku on each paper to extract:
- Study design, sample size, population, intervention, outcomes
- Named entities (genes, proteins, diseases, drugs)
- Claims (causal, associative, mechanistic)
- Mechanisms (upstream/downstream entity, interaction type)
- Methods, key findings, limitations

```bash
python -m decoded.extract.worker --limit 50 --model claude-haiku-4-5-20251001
```

### D4: Graph (`decoded/graph/`)

Builds a Neo4j knowledge graph with:
- **Paper** nodes (title, DOI, journal, abstract)
- **Researcher** nodes (deduplicated by name)
- **Entity** nodes (deduplicated by SHA1 of normalized text+type)
- **Claim** nodes (per-paper)
- **Mechanism** nodes (upstream/downstream/interaction)
- **Method** nodes (deduplicated by name)

Relationships: `AUTHORED_BY`, `HAS_ENTITY`, `MAKES_CLAIM`, `DESCRIBES_MECHANISM`, `USES_METHOD`, `CITES`, `CONNECTS`

```bash
python -m decoded.graph.worker --limit 200
python -m decoded.graph.worker --verify-only  # count nodes/edges
```

**Current graph:** 878 nodes, 846 edges across 100 papers.

### D5: Connect (`decoded/connect/`)

**Three-phase connection discovery:**

1. **Graph phase** — Neo4j queries for shared entities, convergent claims, shared mechanisms, methodological parallels
2. **Embedding phase** — pgvector cosine similarity (requires `OPENAI_API_KEY`)
3. **LLM phase** — Claude Sonnet validates top candidates, classifies connection type

**Connection types:** `replicates`, `contradicts`, `extends`, `mechanism_for`, `shares_target`, `convergent_evidence`, `methodological_parallel`

```bash
python -m decoded.connect.worker --phase graph,llm --limit 20
```

**On-demand BRIDGE QUERY** — given two concepts, find the connection path:

```bash
python -m decoded.connect.worker --bridge "A-FABP" "neuroinflammation"
```

Returns: graph paths (≤4 hops) + semantically similar papers + LLM bridge hypothesis.

### D6: Critique (`decoded/critique/`)

Generates Intelligence Briefs using Claude Sonnet. Papers are ranked by impact score:

```
impact = connection_count × 3 + entity_count + claim_count
```

Each brief scores:
- **Methodology** (0–10): study design, controls, sample size
- **Reproducibility** (0–10): methods clarity, data/code availability
- **Novelty** (0–10): findings vs. existing literature
- **Statistical rigor** (0–10): appropriate tests, effect sizes, p-hacking risk

```bash
python -m decoded.critique.worker --limit 5
python -m decoded.critique.worker --min-connections 2  # only well-connected papers
```

### D7: API (`decoded/api/`)

FastAPI server with 14 endpoints:

| Method | Path | Description |
|--------|------|-------------|
| GET | `/papers` | List papers with filtering |
| GET | `/papers/{id}` | Paper detail with extraction |
| GET | `/papers/{id}/connections` | Connections for a paper |
| GET | `/papers/{id}/critique` | Intelligence Brief |
| GET | `/connections` | All connections with filtering |
| GET | `/connections/convergences` | High-confidence convergence zones |
| GET | `/gaps` | Research gaps (connected, uncritiqued) |
| GET | `/search?q=` | Full-text search |
| POST | `/analyze` | On-demand DOI analysis |
| POST | `/bridge` | Concept-to-concept bridge query |
| GET | `/stats` | Pipeline statistics |
| GET | `/health` | Health check |

```bash
python -m uvicorn decoded.api.main:app --port 8000
# Docs: http://localhost:8000/docs
```

### D8: Outreach (`decoded/outreach/`)

Author outreach system with safety rails:

- **Email extraction**: PubMed API author contact lookup via DOI/PMID
- **Template generation**: Claude Sonnet personalized emails (AI disclosed in first paragraph)
- **Queue**: SQLite-backed, 90-day per-author cooldown, unsubscribe tracking
- **Safety**: manual approval before sending, one-at-a-time dispatch

```bash
# Generate 3 sample emails (print only, don't queue)
python -m decoded.outreach.worker --generate 3 --dry-run

# Add to queue (requires manual approval before sending)
python -m decoded.outreach.worker --generate 10

# Manage queue
python -m decoded.outreach.worker --list
python -m decoded.outreach.worker --stats
python -m decoded.outreach.worker --unsubscribe author@university.edu
```

---

## Database Schema

### PostgreSQL (`encoded_human`)

| Table | Description |
|-------|-------------|
| `raw_papers` | Papers from all sources |
| `ingest_runs` | Ingest pipeline run log |
| `extraction_results` | LLM-extracted structured data + embeddings |
| `discovered_connections` | LLM-validated paper-to-paper connections |
| `paper_critiques` | Intelligence Briefs |

### Neo4j

**Nodes:** Paper, Researcher, Entity, Claim, Mechanism, Method

**Edges:** AUTHORED_BY, HAS_ENTITY, MAKES_CLAIM, DESCRIBES_MECHANISM, USES_METHOD, CITES, CONNECTS

---

## Configuration

Set in `.env`:

```bash
DATABASE_URL=postgresql://user@localhost:5432/encoded_human
NEO4J_URI=bolt://localhost:7687
NEO4J_USER=neo4j
NEO4J_PASSWORD=decoded123
REDIS_URL=redis://localhost:6379/0
ANTHROPIC_API_KEY=sk-ant-...
OPENAI_API_KEY=sk-...  # optional, for pgvector embeddings
NCBI_API_KEY=...       # optional, increases PubMed rate limit
```

---

## Cost Model

As of March 2026, approximate costs per paper:

| Step | Model | Cost/paper |
|------|-------|-----------|
| Extraction | Claude Haiku | ~$0.007 |
| Connection validation | Claude Sonnet | ~$0.008 |
| Intelligence Brief | Claude Sonnet | ~$0.014 |
| Outreach email | Claude Sonnet | ~$0.007 |
| **Total pipeline** | | **~$0.036/paper** |

100 papers = ~$3.60 end-to-end.

---

## Project Structure

```
decoded/
├── models/         D1: Pydantic models
├── config/         D1: Domain seed config
├── queue.py        D1: Redis job queue
├── cost_tracker.py D1: LLM cost tracking
├── ingest/         D2: PMC/PubMed ingest
├── extract/        D3: LLM extraction
├── graph/          D4: Neo4j graph builder
├── connect/        D5: Connection discovery
├── critique/       D6: Intelligence Briefs
├── api/            D7: FastAPI server
└── outreach/       D8: Author email system
migrations/         SQL + Cypher schema files
tests/              Test suite
```
