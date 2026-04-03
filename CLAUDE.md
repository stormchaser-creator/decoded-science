# Decoded — Session Orientation

**What:** Decoded is a literature connectome pipeline that ingests biomedical research papers, extracts structured knowledge (claims, methods, findings), builds a Neo4j graph of connections between papers, and produces Intelligence Briefs. Outputs feed into Pearl (The Encoded Human) via a bridge not yet built.

**Stack:** Python 3.12, FastAPI, PostgreSQL 17 (`encoded_human` DB — shared with Pearl), Neo4j, Redis, Anthropic Claude API, PM2.

**Status (as of 2026-04-02):** 8-stage pipeline running. 60,588+ raw_papers, 17,278 extracted, 13,512 connections, 830 Intelligence Briefs. Bulk PMC downloader active.

---

## Architecture

### Database
- **PostgreSQL 17** (`encoded_human` DB — same database as The Encoded Human / Pearl)
- Key tables: `raw_papers`, `paper_extractions`, `paper_connections`, `intelligence_briefs`
- Neo4j graph: paper nodes + relationship edges (concept co-occurrence, citation, semantic)

### 8-Stage Pipeline

```
Ingest → Extract → Graph → Connect → Critique → API → Pearl Bridge → Outreach
```

1. **Ingest** (`decoded/ingest/`): Pull papers from PubMed/PMC. `bulk_pmc.py` handles bulk PMC downloads.
2. **Extract** (`decoded/extract/`): Claude Haiku extracts structured claims, methods, findings from full text.
3. **Graph** (`decoded/graph/`): Sync extracted papers to Neo4j as nodes + relationships.
4. **Connect** (`decoded/connect/`): 3-phase connection discovery — BM25 similarity, semantic embedding, LLM-verified concept bridges.
5. **Critique** (`decoded/critique/`): Claude Sonnet generates Intelligence Briefs (critical analysis + synthesis).
6. **API** (`decoded/api/`): FastAPI REST API + Pearl connectome endpoint. Port 8000.
7. **Pearl Bridge** (`decoded/pearl/`): NOT YET BUILT. Bridges `raw_papers` → Pearl's `kb_entries`. Architecture decided: batch cron, claims-first, Pearl overrides classification.
8. **Outreach** (`decoded/outreach/`): Downstream publishing (not yet wired).

### PM2 Processes (`ecosystem.config.js`)
- `decoded-api` — FastAPI + uvicorn, port 8000, 2 workers, autorestart: true
- `decoded-extract` — Paper extraction worker (Claude Haiku), autorestart: **false** (run manually)
- `decoded-graph` — Neo4j sync worker, autorestart: true, backoff 300s when idle
- `decoded-connect` — Connection discovery worker, autorestart: **false** (run manually)
- `decoded-critique` — Intelligence Brief generator (Claude Sonnet), autorestart: **false**
- `decoded-explorer` — Vite React frontend, port 5173, autorestart: true

**Important:** `decoded-extract`, `decoded-connect`, `decoded-critique` have `autorestart: false` and `max_restarts: 0` to control API costs. Run manually or restart via `pm2 restart <name>`.

### API Endpoints (`decoded/api/main.py`)
- `GET /papers` — list papers with filters
- `GET /papers/{id}` — paper detail + extraction
- `GET /connections` — connection graph
- `GET /briefs` — Intelligence Briefs
- `GET /connectome` — Pearl bridge endpoint (JSON graph for Pearl tools)
- Auth: `DECODED_JWT_SECRET` in `.env`

### Shared Library
`/Users/whit/Projects/shared-libs/pubmed-tools/` — extracted from Pearl's PubMed fetcher:
- `PubMedSearcher` — search PubMed by query/filters
- `PubMedFetcher` — fetch full text from PMC
- `MetadataExtractor` — normalize paper metadata
- `CitationVerifier` — validate citation strings

Both Decoded and Pearl import from this shared lib.

---

## Data Numbers (as of 2026-04-02)

| Table | Count |
|-------|-------|
| raw_papers | 60,588+ |
| paper_extractions | 17,278 |
| paper_connections | 13,512 |
| intelligence_briefs | 830 |

**Bulk PMC corpus:**
- 579K aging-related PMIDs indexed
- 171K with OA (open access) full text available
- `oa_file_list.csv` (910MB) on disk
- NCBI API key wired in `.env` as `NCBI_API_KEY`
- Bulk PMC download running as of 2026-04-02 (PID 84167, log: `/tmp/pmc_bulk_download.log`)

---

## Recent Changes (April 1–2, 2026)

### April 1 — Consolidation
- `decoded/ingest/discover.py` refactored to use `shared-libs/pubmed-tools` instead of inline PubMed code
- Workers restarted April 2

### April 2 — Bulk PMC
- `decoded/ingest/bulk_pmc.py` updated with `.nxml` extension handling + transaction recovery
- Bulk PMC download job started (PID 84167)
- NCBI API key now wired in `.env`

---

## Environment Variables (`.env`)

- `ANTHROPIC_API_KEY` — Claude API key (shared key, not segregated like Pearl's)
- `NEO4J_PASSWORD` — Neo4j auth
- `DECODED_JWT_SECRET` — API auth signing secret
- `NCBI_API_KEY` — NCBI Entrez API key (rate limit: 10 req/sec vs 3 without)
- `DATABASE_URL` — `postgresql://whit@localhost:5432/encoded_human`
- `NEO4J_URI` — `bolt://localhost:7687`
- `REDIS_URL` — `redis://localhost:6379/0`

---

## Key Commands

```bash
# Start all workers
pm2 start ecosystem.config.js

# Run extraction manually (cost-controlled)
pm2 restart decoded-extract

# Check bulk PMC download
tail -f /tmp/pmc_bulk_download.log

# DB inspection
psql -d encoded_human -c "SELECT COUNT(*) FROM raw_papers;"
psql -d encoded_human -c "SELECT COUNT(*) FROM paper_extractions;"
psql -d encoded_human -c "SELECT COUNT(*) FROM paper_connections;"
psql -d encoded_human -c "SELECT COUNT(*) FROM intelligence_briefs;"

# API health
curl http://localhost:8000/health

# Run ingest pipeline
cd /Users/whit/Projects/Decoded && source .venv/bin/activate && python -m decoded.ingest.discover

# Run bulk PMC importer
cd /Users/whit/Projects/Decoded && source .venv/bin/activate && python decoded/ingest/bulk_pmc.py
```

---

## Project Structure

```
/Decoded/
├── CLAUDE.md               # This file
├── ecosystem.config.js     # PM2 process configs
├── pyproject.toml          # Python deps
├── decoded/
│   ├── api/                # FastAPI app
│   ├── config/             # Settings, constants
│   ├── connect/            # Connection discovery worker
│   ├── critique/           # Intelligence Brief generator
│   ├── extract/            # Paper extraction worker
│   ├── graph/              # Neo4j sync worker
│   ├── ingest/             # Paper ingestion (PubMed, PMC bulk)
│   ├── models/             # Pydantic models
│   ├── outreach/           # Publishing pipeline (not yet wired)
│   ├── pearl/              # Pearl bridge (NOT YET BUILT)
│   └── queue.py            # Job queue abstraction
├── explorer/               # Vite React frontend (port 5173)
├── migrations/             # DB migrations
├── scripts/                # Utility scripts
├── data/                   # Local data files
└── logs/                   # PM2 log files
```

---

## Known Issues / Pending

- **Pearl bridge (`decoded/pearl/`):** NOT BUILT. Architecture decided: batch cron job reads `raw_papers`, converts claims to `kb_entries` format, Pearl overrides on classification confidence. 27 Altini papers are the first target batch.
- **Outreach pipeline:** `decoded/outreach/` directory exists but not wired to any publishing target.
- **Connection coverage:** 13,512 connections out of 17,278 extracted papers = ~78% coverage. Some papers have no connections yet.
- **Explorer frontend:** Served via `vite preview` (not production build). For production, should be built and served via nginx.

---

## Cross-Project Connections

- **The Encoded Human** (`~/Projects/The-Encoded-Human/`): Pearl is the downstream consumer of Decoded's knowledge. Same PostgreSQL DB. Bridge not yet built.
- **shared-libs/pubmed-tools** (`~/Projects/shared-libs/pubmed-tools/`): Shared PubMed tooling used by both Decoded and Pearl.
- **AutoAIBiz** (`~/Projects/AutoAIBiz/`): Reach agent can potentially publish Intelligence Briefs to Substack/X.
