"""Decoded FastAPI server — REST API for the literature connectome.

Endpoints:
  GET  /papers                  — list papers with filtering
  GET  /papers/{id}             — single paper detail
  GET  /papers/{id}/connections — connections for a paper
  GET  /papers/{id}/critique    — critique for a paper
  GET  /connections             — list all connections
  GET  /connections/convergences — high-confidence convergences
  GET  /gaps                    — research gaps (highly connected but uncritiqued)
  GET  /search                  — full-text search across papers
  POST /analyze                 — on-demand DOI analysis trigger
  POST /bridge                  — on-demand bridge query between two concepts
  GET  /stats                   — pipeline statistics
  GET  /health                  — health check

Auth & Workspace Endpoints:
  POST /auth/register           — create account
  POST /auth/login              — login, returns JWT
  GET  /auth/profile            — current user profile (requires JWT)
  GET  /workspace/searches      — list saved searches
  POST /workspace/searches      — save a search
  DELETE /workspace/searches/{id} — delete saved search
  GET  /workspace/collections   — list collections
  POST /workspace/collections   — create collection
  POST /workspace/collections/{id}/papers — add paper to collection
  DELETE /workspace/collections/{id}/papers/{paper_id} — remove paper
  GET  /workspace/collections/{id}/export — export BibTeX or CSV
  GET  /workspace/watchlists    — list watchlists
  POST /workspace/watchlists    — create watchlist
  DELETE /workspace/watchlists/{id} — delete watchlist
  GET  /workspace/workspaces    — list workspaces
  POST /workspace/workspaces    — create workspace
  PUT  /workspace/workspaces/{id} — update workspace state
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any

import redis
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr
from typing import Optional

from decoded.api.auth import hash_password, verify_password, create_access_token, decode_token

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=False)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("decoded.api")

app = FastAPI(
    title="Decoded",
    description="Literature connectome — AI-discovered connections in scientific research",
    version="0.1.0",
)

_cors_origins = os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,https://connectome.theencodedhuman.com,https://thedecodedhuman.com",
).split(",")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _cors_origins],
    allow_methods=["GET", "HEAD", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)

# Cache-Control header mapping (path prefix → max-age seconds)
_CACHE_RULES = {
    "/v1/stats": 60,
    "/v1/graph/overview": 300,
    "/papers": 30,
    "/connections": 30,
}


@app.middleware("http")
async def add_cache_headers(request, call_next):
    response = await call_next(request)
    if request.method == "GET":
        for prefix, max_age in _CACHE_RULES.items():
            if request.url.path.startswith(prefix):
                response.headers["Cache-Control"] = f"public, max-age={max_age}"
                break
    return response


# ---------------------------------------------------------------------------
# DB connection pool
# ---------------------------------------------------------------------------

import psycopg2.pool

_db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
_db_pool = psycopg2.pool.ThreadedConnectionPool(minconn=2, maxconn=20, dsn=_db_url)

_redis_url = os.environ.get("REDIS_URL", "redis://localhost:6379/0")
try:
    _redis = redis.from_url(_redis_url, decode_responses=True)
    _redis.ping()
except Exception:
    _redis = None
    logger.warning("Redis not available — caching disabled")


def get_db():
    conn = _db_pool.getconn()
    psycopg2.extras.register_uuid(conn)
    return conn


def release_db(conn):
    """Return connection to pool (call instead of release_db(conn))."""
    if conn:
        try:
            conn.rollback()  # reset any uncommitted state
        except Exception:
            pass
        _db_pool.putconn(conn)


def _jsonify_row(row: dict) -> dict:
    """Ensure all JSONB fields are proper Python objects."""
    result = {}
    for k, v in row.items():
        if isinstance(v, str):
            # Try parsing JSONB strings
            try:
                if v.startswith(("[", "{")):
                    result[k] = json.loads(v)
                else:
                    result[k] = v
            except (json.JSONDecodeError, AttributeError):
                result[k] = v
        elif hasattr(v, "isoformat"):  # date/datetime
            result[k] = v.isoformat()
        else:
            result[k] = v
    return result


# ---------------------------------------------------------------------------
# Request / response models
# ---------------------------------------------------------------------------

class AnalyzeRequest(BaseModel):
    doi: str
    priority: int = 0


class BridgeRequest(BaseModel):
    concept_a: str
    concept_b: str
    max_hops: int = 4


# Auth models
class RegisterRequest(BaseModel):
    email: EmailStr
    name: str
    password: str  # min length enforced in endpoint


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


# Workspace models
class SavedSearchCreate(BaseModel):
    name: str
    query: str
    filters: dict = {}


class CollectionCreate(BaseModel):
    name: str
    description: Optional[str] = None
    is_public: bool = False


class AddPaperRequest(BaseModel):
    paper_id: str
    notes: Optional[str] = None


class WatchlistCreate(BaseModel):
    name: str
    watch_type: str  # entity | query | author
    watch_value: str


class WorkspaceCreate(BaseModel):
    name: str
    description: Optional[str] = None
    state: dict = {}
    is_default: bool = False


class WorkspaceUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    state: Optional[dict] = None


class ConnectomeQueryRequest(BaseModel):
    question: str
    concept_a: Optional[str] = None
    concept_b: Optional[str] = None
    query_type: str = "bridge"  # bridge | neighbors | pathway | text_search
    max_results: int = 10


# ---------------------------------------------------------------------------
# Auth helpers (must be defined before endpoints that use Depends)
# ---------------------------------------------------------------------------

def get_current_user(authorization: Optional[str] = Header(None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Missing or invalid Authorization header")
    token = authorization.split(" ", 1)[1]
    payload = decode_token(token)
    if not payload:
        raise HTTPException(status_code=401, detail="Invalid or expired token")
    return payload


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        release_db(conn)
        db_ok = True
    except Exception:
        db_ok = False

    return {"status": "ok" if db_ok else "degraded", "db": db_ok}


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@app.get("/stats")
def stats():
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT status, count(*) as n FROM raw_papers GROUP BY status ORDER BY n DESC")
    paper_stats = {r["status"]: r["n"] for r in cur.fetchall()}

    cur.execute("SELECT count(*) as n FROM raw_papers")
    total_papers = cur.fetchone()["n"]

    cur.execute("SELECT count(*) as n FROM extraction_results")
    total_extractions = cur.fetchone()["n"]

    cur.execute("SELECT count(*) as n FROM discovered_connections")
    total_connections = cur.fetchone()["n"]

    cur.execute("SELECT count(*) as n FROM paper_critiques")
    total_critiques = cur.fetchone()["n"]

    cur.execute(
        "SELECT connection_type, count(*) as n FROM discovered_connections GROUP BY connection_type ORDER BY n DESC"
    )
    connection_types = {r["connection_type"]: r["n"] for r in cur.fetchall()}

    cur.execute(
        "SELECT coalesce(sum(cost_usd), 0) as total FROM extraction_results"
    )
    extract_cost = float(cur.fetchone()["total"])

    cur.execute(
        "SELECT coalesce(sum(cost_usd), 0) as total FROM discovered_connections"
    )
    connect_cost = float(cur.fetchone()["total"])

    cur.execute(
        "SELECT coalesce(sum(cost_usd), 0) as total FROM paper_critiques"
    )
    critique_cost = float(cur.fetchone()["total"])

    release_db(conn)
    return {
        "papers": {"total": total_papers, "by_status": paper_stats},
        "extractions": total_extractions,
        "connections": {"total": total_connections, "by_type": connection_types},
        "critiques": total_critiques,
        "cost_usd": {
            "extraction": round(extract_cost, 4),
            "connection": round(connect_cost, 4),
            "critique": round(critique_cost, 4),
            "total": round(extract_cost + connect_cost + critique_cost, 4),
        },
    }


# ---------------------------------------------------------------------------
# Papers
# ---------------------------------------------------------------------------

@app.get("/papers")
def list_papers(
    status: str | None = Query(None),
    source: str | None = Query(None),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
    order_by: str = Query("created_at"),
):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    where_clauses = ["p.title IS NOT NULL"]
    params: list[Any] = []

    status_filter = status or "extracted"
    where_clauses.append("p.status = %s")
    params.append(status_filter)
    if source:
        where_clauses.append("p.source = %s")
        params.append(source)

    valid_order = {"created_at", "published_date", "title", "citation_count"}
    order_col = order_by if order_by in valid_order else "created_at"

    where = " AND ".join(where_clauses)
    cur.execute(
        f"""
        SELECT p.id, p.title, p.authors, p.journal, p.doi, p.source,
               p.published_date, p.status, p.citation_count,
               COUNT(DISTINCT dc.id) as connection_count,
               (SELECT pc.overall_quality FROM paper_critiques pc WHERE pc.paper_id = p.id LIMIT 1) as critique_quality
        FROM raw_papers p
        LEFT JOIN discovered_connections dc ON dc.paper_a_id = p.id OR dc.paper_b_id = p.id
        WHERE {where}
        GROUP BY p.id, p.title, p.authors, p.journal, p.doi, p.source,
                 p.published_date, p.status, p.citation_count
        ORDER BY p.{order_col} DESC NULLS LAST
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]

    cur.execute(f"SELECT count(*) as n FROM raw_papers p WHERE {where}", params)
    total = cur.fetchone()["n"]

    release_db(conn)
    return {"papers": rows, "total": total, "limit": limit, "offset": offset}


@app.get("/papers/{paper_id}")
def get_paper(paper_id: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT p.*,
               e.study_design, e.sample_size, e.population,
               e.intervention, e.comparator, e.primary_outcome,
               e.secondary_outcomes, e.entities, e.claims,
               e.mechanisms, e.methods, e.key_findings, e.limitations,
               e.funding_sources, e.conflicts_of_interest
        FROM raw_papers p
        LEFT JOIN extraction_results e ON e.paper_id = p.id
        WHERE p.id = %s
        """,
        (paper_id,),
    )
    row = cur.fetchone()
    release_db(conn)
    if not row:
        raise HTTPException(status_code=404, detail="Paper not found")
    return _jsonify_row(dict(row))


@app.get("/papers/{paper_id}/connections")
def get_paper_connections(paper_id: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT dc.*,
               p_a.title as paper_a_title,
               p_b.title as paper_b_title
        FROM discovered_connections dc
        JOIN raw_papers p_a ON p_a.id = dc.paper_a_id
        JOIN raw_papers p_b ON p_b.id = dc.paper_b_id
        WHERE (dc.paper_a_id = %s OR dc.paper_b_id = %s)
          AND dc.connection_type != 'replicates'
        ORDER BY dc.confidence DESC
        """,
        (paper_id, paper_id),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]
    release_db(conn)
    return {"paper_id": paper_id, "connections": rows, "count": len(rows)}


@app.get("/critiques")
def list_critiques(
    limit: int = Query(20, le=100),
    skip: int = Query(0),
    quality: str | None = Query(None),  # high | medium | low
):
    """List all intelligence briefs (paper critiques) with paper metadata."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    quality_filter = ""
    if quality == "high":
        quality_filter = "AND pc.overall_quality = 'high'"
    elif quality == "medium":
        quality_filter = "AND pc.overall_quality = 'medium'"
    elif quality == "low":
        quality_filter = "AND pc.overall_quality = 'low'"

    cur.execute(
        f"""
        SELECT pc.id, pc.paper_id, pc.overall_quality, pc.summary as brief, pc.strengths,
               pc.weaknesses, pc.red_flags, pc.recommendation,
               pc.methodology_score, pc.novelty_score, pc.reproducibility_score,
               pc.created_at, p.title as paper_title, p.journal, p.published_date,
               (SELECT COUNT(*) FROM discovered_connections dc
                WHERE dc.paper_a_id = pc.paper_id OR dc.paper_b_id = pc.paper_id) as connection_count
        FROM paper_critiques pc
        JOIN raw_papers p ON p.id = pc.paper_id
        WHERE COALESCE(pc.brief_confidence, '') != 'insufficient' {quality_filter}
        ORDER BY pc.methodology_score DESC NULLS LAST, pc.created_at DESC
        LIMIT %s OFFSET %s
        """,
        (limit, skip),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]

    count_query = f"SELECT COUNT(*) as n FROM paper_critiques pc WHERE COALESCE(pc.brief_confidence, '') != 'insufficient' {quality_filter}"
    cur.execute(count_query)
    total = cur.fetchone()["n"]
    release_db(conn)
    return {"critiques": rows, "total": total, "count": len(rows)}


@app.get("/v1/briefs")
def list_briefs_v1(
    limit: int = Query(20, le=100),
    skip: int = Query(0),
    quality: str | None = Query(None),
):
    """Alias for /critiques — intelligence briefs with full metadata."""
    return list_critiques(limit=limit, skip=skip, quality=quality)


@app.get("/papers/{paper_id}/entities")
def get_paper_entities(paper_id: str):
    """Get extracted entities and claims for a paper."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT entities, claims, mechanisms, methods, key_findings FROM extraction_results WHERE paper_id = %s LIMIT 1",
        (paper_id,),
    )
    row = cur.fetchone()
    release_db(conn)
    if not row:
        raise HTTPException(status_code=404, detail="No extraction data for this paper")
    return _jsonify_row(dict(row))


@app.get("/papers/{paper_id}/critique")
def get_paper_critique(paper_id: str):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM paper_critiques WHERE paper_id = %s ORDER BY created_at DESC LIMIT 1",
        (paper_id,),
    )
    row = cur.fetchone()
    release_db(conn)
    if not row:
        raise HTTPException(status_code=404, detail="No critique found for this paper")
    return _jsonify_row(dict(row))


# ---------------------------------------------------------------------------
# Connections
# ---------------------------------------------------------------------------

@app.get("/connections")
def list_connections(
    connection_type: str | None = Query(None),
    min_confidence: float = Query(0.5),
    limit: int = Query(50, le=200),
    offset: int = Query(0),
):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    where_clauses = ["dc.confidence >= %s", "dc.connection_type != 'replicates'"]
    params: list[Any] = [min_confidence]

    if connection_type:
        where_clauses.append("dc.connection_type = %s")
        params.append(connection_type)

    where = " AND ".join(where_clauses)
    cur.execute(
        f"""
        SELECT dc.*,
               p_a.title as paper_a_title,
               p_b.title as paper_b_title
        FROM discovered_connections dc
        JOIN raw_papers p_a ON p_a.id = dc.paper_a_id
        JOIN raw_papers p_b ON p_b.id = dc.paper_b_id
        WHERE {where}
        ORDER BY dc.confidence DESC, dc.novelty_score DESC
        LIMIT %s OFFSET %s
        """,
        (*params, limit, offset),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]

    cur.execute(f"SELECT count(*) as n FROM discovered_connections dc WHERE {where}", params)
    total = cur.fetchone()["n"]

    release_db(conn)
    return {"connections": rows, "total": total}


@app.get("/connections/convergences")
def get_convergences(
    min_confidence: float = Query(0.7),
    limit: int = Query(20, le=100),
):
    """Papers with multiple high-confidence connections — convergence zones."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT p.id, p.title, p.doi,
               COUNT(DISTINCT dc.id) as connection_count,
               AVG(dc.confidence) as avg_confidence,
               ARRAY_AGG(DISTINCT dc.connection_type) as connection_types
        FROM raw_papers p
        JOIN discovered_connections dc
            ON dc.paper_a_id = p.id OR dc.paper_b_id = p.id
        WHERE dc.confidence >= %s AND dc.connection_type != 'replicates'
        GROUP BY p.id, p.title, p.doi
        HAVING COUNT(DISTINCT dc.id) >= 2
        ORDER BY connection_count DESC, avg_confidence DESC
        LIMIT %s
        """,
        (min_confidence, limit),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]
    release_db(conn)
    return {"convergences": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Gaps
# ---------------------------------------------------------------------------

@app.get("/gaps")
def get_gaps(limit: int = Query(20, le=100)):
    """Research gaps: well-connected papers with no critique yet."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT p.id, p.title, p.doi, p.journal, p.published_date,
               COUNT(DISTINCT dc.id) as connection_count,
               p.status
        FROM raw_papers p
        JOIN discovered_connections dc
            ON dc.paper_a_id = p.id OR dc.paper_b_id = p.id
        WHERE NOT EXISTS (
            SELECT 1 FROM paper_critiques pc WHERE pc.paper_id = p.id
        )
        GROUP BY p.id, p.title, p.doi, p.journal, p.published_date, p.status
        ORDER BY connection_count DESC
        LIMIT %s
        """,
        (limit,),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]
    release_db(conn)
    return {"gaps": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Search
# ---------------------------------------------------------------------------

@app.get("/search")
def search(
    q: str = Query(..., min_length=2),
    limit: int = Query(20, le=100),
):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Use full-text search with GIN index (much faster than ILIKE at scale)
    tsquery = " & ".join(word for word in q.split() if word)
    cur.execute(
        """
        SELECT p.id, p.title, p.abstract, p.authors, p.journal,
               p.doi, p.published_date, p.status,
               COUNT(DISTINCT dc.id) as connection_count,
               ts_rank(p.search_vector, to_tsquery('english', %s)) as rank
        FROM raw_papers p
        LEFT JOIN discovered_connections dc ON dc.paper_a_id = p.id OR dc.paper_b_id = p.id
        WHERE p.search_vector @@ to_tsquery('english', %s)
        GROUP BY p.id, p.title, p.abstract, p.authors, p.journal,
                 p.doi, p.published_date, p.status
        ORDER BY rank DESC, connection_count DESC
        LIMIT %s
        """,
        (tsquery, tsquery, limit),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]
    release_db(conn)
    return {"query": q, "results": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# On-demand analysis
# ---------------------------------------------------------------------------

@app.post("/analyze", deprecated=True)
async def analyze_doi(request: AnalyzeRequest, background_tasks: BackgroundTasks, current_user: dict = Depends(get_current_user)):
    """Deprecated: use POST /v1/papers/analyze instead. Triggers on-demand analysis of a paper by DOI."""
    background_tasks.add_task(_run_doi_analysis, request.doi, request.priority)
    return {
        "status": "queued",
        "doi": request.doi,
        "message": "Deprecated — use POST /v1/papers/analyze for job tracking. Analysis started in background.",
    }


def _run_doi_analysis(doi: str, priority: int = 0) -> None:
    """Background task: fetch, extract, and connect a paper by DOI."""
    try:
        from decoded.api.analysis_worker import AnalysisWorker
        worker = AnalysisWorker()
        worker.analyze_doi(doi, priority=priority)
    except Exception as exc:
        logger.error("DOI analysis failed for %s: %s", doi, exc, exc_info=True)


# ---------------------------------------------------------------------------
# Bridge query
# ---------------------------------------------------------------------------

@app.post("/bridge")
def bridge_query(request: BridgeRequest, current_user: dict = Depends(get_current_user)):
    """On-demand bridge query: find/build connection between two concepts (requires auth)."""
    import json as _json
    from decoded.connect.worker import BridgeQueryWorker
    worker = BridgeQueryWorker()
    result = worker.query(
        concept_a=request.concept_a,
        concept_b=request.concept_b,
        max_hops=request.max_hops,
    )
    graph_paths = result.get("graph_paths", [])
    hypothesis_text = result.get("hypothesis", {}).get("hypothesis") if result.get("hypothesis") else None
    cost = result.get("hypothesis", {}).get("cost_usd", 0) if result.get("hypothesis") else 0
    path_found = len(graph_paths) > 0 or bool(hypothesis_text)
    path_type = "graph_traversal" if graph_paths else ("llm_hypothesis" if hypothesis_text else "none")

    # Cache result for future identical queries
    try:
        a, b = sorted([request.concept_a.lower().strip(), request.concept_b.lower().strip()])
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO bridge_results
                (concept_a, concept_b, path_found, path_type, path_data, hypothesis, cost_usd)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (concept_a, concept_b)
            DO UPDATE SET
                query_count = bridge_results.query_count + 1,
                path_found = EXCLUDED.path_found,
                path_type = EXCLUDED.path_type,
                path_data = EXCLUDED.path_data,
                hypothesis = EXCLUDED.hypothesis,
                cost_usd = EXCLUDED.cost_usd
            """,
            (a, b, path_found, path_type,
             _json.dumps(graph_paths[:5]) if graph_paths else None,
             hypothesis_text, cost),
        )
        conn.commit()
        release_db(conn)
    except Exception as exc:
        logger.warning("Bridge cache write failed: %s", exc)

    return {
        "concept_a": result["concept_a"],
        "concept_b": result["concept_b"],
        "graph_paths": graph_paths,
        "graph_paths_found": len(graph_paths),
        "papers_a": result.get("papers_a", [])[:5],
        "papers_b": result.get("papers_b", [])[:5],
        "papers_a_count": len(result.get("papers_a", [])),
        "papers_b_count": len(result.get("papers_b", [])),
        "similar_papers": result.get("similar_papers", [])[:5],
        "hypothesis": hypothesis_text,
        "cost_usd": cost,
    }


# ---------------------------------------------------------------------------
# Connectome query (Pearl integration)
# ---------------------------------------------------------------------------

@app.post("/connectome/query")
def connectome_query(request: ConnectomeQueryRequest):
    """Query the literature connectome graph — called by Pearl's query_connectome tool."""
    from decoded.pearl.graph_tool import query_connectome
    result = query_connectome(
        question=request.question,
        concept_a=request.concept_a,
        concept_b=request.concept_b,
        query_type=request.query_type,
        max_results=min(request.max_results, 20),
    )
    return result


@app.get("/connectome/stats")
def connectome_pearl_stats():
    """Stats on what's been bridged to Pearl's KB from Decoded."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT entry_type, operation, density, count(*) as n
        FROM kb_entries
        WHERE workstation = 'decoded_connectome'
        GROUP BY entry_type, operation, density
        ORDER BY n DESC
        """
    )
    rows = [dict(r) for r in cur.fetchall()]
    cur.execute("SELECT count(*) as n FROM kb_entries WHERE workstation = 'decoded_connectome'")
    total = cur.fetchone()["n"]
    release_db(conn)
    return {"total_entries": total, "breakdown": rows}


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------


# ---------------------------------------------------------------------------
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/auth/register", status_code=201)
def register(request: RegisterRequest):
    if len(request.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id FROM decoded_users WHERE email = %s", (request.email,))
    if cur.fetchone():
        release_db(conn)
        raise HTTPException(status_code=409, detail="Email already registered")
    pw_hash = hash_password(request.password)
    cur.execute(
        "INSERT INTO decoded_users (email, name, password_hash) VALUES (%s, %s, %s) RETURNING id, email, name, role, created_at",
        (request.email, request.name, pw_hash),
    )
    user = dict(cur.fetchone())
    conn.commit()
    release_db(conn)
    user["created_at"] = user["created_at"].isoformat() if user.get("created_at") else None
    token = create_access_token(str(user["id"]), user["email"])
    return {"user": user, "token": token}


@app.post("/auth/login")
def login(request: LoginRequest):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, email, name, role, password_hash FROM decoded_users WHERE email = %s", (request.email,))
    row = cur.fetchone()
    release_db(conn)
    if not row or not verify_password(request.password, row["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid credentials")
    user = {k: v for k, v in row.items() if k != "password_hash"}
    token = create_access_token(str(user["id"]), user["email"])
    return {"user": user, "token": token}


@app.get("/auth/profile")
def profile(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id, email, name, role, created_at FROM decoded_users WHERE id = %s",
        (current_user["sub"],),
    )
    row = cur.fetchone()
    release_db(conn)
    if not row:
        raise HTTPException(status_code=404, detail="User not found")
    user = dict(row)
    user["created_at"] = user["created_at"].isoformat() if user.get("created_at") else None
    return user


# ---------------------------------------------------------------------------
# Saved searches
# ---------------------------------------------------------------------------

@app.get("/workspace/searches")
def list_searches(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id, name, query, filters, result_count, last_run_at, created_at FROM saved_searches WHERE user_id = %s ORDER BY created_at DESC",
        (current_user["sub"],),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]
    release_db(conn)
    return {"searches": rows}


@app.post("/workspace/searches", status_code=201)
def create_search(request: SavedSearchCreate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "INSERT INTO saved_searches (user_id, name, query, filters) VALUES (%s, %s, %s, %s) RETURNING id, name, query, filters, created_at",
        (current_user["sub"], request.name, request.query, json.dumps(request.filters)),
    )
    row = _jsonify_row(dict(cur.fetchone()))
    conn.commit()
    release_db(conn)
    return row


@app.delete("/workspace/searches/{search_id}", status_code=204)
def delete_search(search_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM saved_searches WHERE id = %s AND user_id = %s",
        (search_id, current_user["sub"]),
    )
    conn.commit()
    release_db(conn)


# ---------------------------------------------------------------------------
# Collections
# ---------------------------------------------------------------------------

@app.get("/workspace/collections")
def list_collections(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT c.id, c.name, c.description, c.is_public, c.created_at,
               COUNT(cp.paper_id) as paper_count
        FROM decoded_collections c
        LEFT JOIN collection_papers cp ON cp.collection_id = c.id
        WHERE c.user_id = %s
        GROUP BY c.id, c.name, c.description, c.is_public, c.created_at
        ORDER BY c.created_at DESC
        """,
        (current_user["sub"],),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]
    release_db(conn)
    return {"collections": rows}


@app.post("/workspace/collections", status_code=201)
def create_collection(request: CollectionCreate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "INSERT INTO decoded_collections (user_id, name, description, is_public) VALUES (%s, %s, %s, %s) RETURNING id, name, description, is_public, created_at",
        (current_user["sub"], request.name, request.description, request.is_public),
    )
    row = _jsonify_row(dict(cur.fetchone()))
    conn.commit()
    release_db(conn)
    return row


@app.post("/workspace/collections/{collection_id}/papers", status_code=201)
def add_paper_to_collection(
    collection_id: str,
    request: AddPaperRequest,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Verify collection ownership
    cur.execute("SELECT id FROM decoded_collections WHERE id = %s AND user_id = %s", (collection_id, current_user["sub"]))
    if not cur.fetchone():
        release_db(conn)
        raise HTTPException(status_code=404, detail="Collection not found")
    cur.execute(
        "INSERT INTO collection_papers (collection_id, paper_id, notes) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
        (collection_id, request.paper_id, request.notes),
    )
    conn.commit()
    release_db(conn)
    return {"status": "added"}


@app.delete("/workspace/collections/{collection_id}/papers/{paper_id}", status_code=204)
def remove_paper_from_collection(
    collection_id: str,
    paper_id: str,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db()
    cur = conn.cursor()
    # Verify ownership before deleting
    cur.execute(
        "SELECT id FROM decoded_collections WHERE id = %s AND user_id = %s",
        (collection_id, current_user["sub"]),
    )
    if not cur.fetchone():
        release_db(conn)
        raise HTTPException(status_code=404, detail="Collection not found")
    cur.execute(
        "DELETE FROM collection_papers WHERE collection_id = %s AND paper_id = %s",
        (collection_id, paper_id),
    )
    conn.commit()
    release_db(conn)


@app.get("/workspace/collections/{collection_id}/export")
def export_collection(
    collection_id: str,
    format: str = Query("bibtex", enum=["bibtex", "csv"]),
    current_user: dict = Depends(get_current_user),
):
    """Export a collection as BibTeX or CSV."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT p.id, p.title, p.authors, p.journal, p.published_date, p.doi,
               p.pmc_id, p.abstract
        FROM collection_papers cp
        JOIN raw_papers p ON p.id = cp.paper_id
        JOIN decoded_collections c ON c.id = cp.collection_id
        WHERE cp.collection_id = %s AND c.user_id = %s
        ORDER BY p.published_date DESC NULLS LAST
        """,
        (collection_id, current_user["sub"]),
    )
    papers = [_jsonify_row(dict(r)) for r in cur.fetchall()]
    release_db(conn)

    if format == "bibtex":
        lines = []
        for p in papers:
            authors = p.get("authors", [])
            if isinstance(authors, list):
                author_str = " and ".join(
                    a.get("name", a) if isinstance(a, dict) else str(a)
                    for a in authors
                )
            else:
                author_str = str(authors)
            doi = p.get("doi", "")
            key = (doi.replace("/", "_").replace(".", "_") if doi else str(p["id"])[:8])
            year = ""
            if p.get("published_date"):
                year = str(p["published_date"])[:4]
            lines.append(f"@article{{{key},")
            lines.append(f'  title = {{{p.get("title", "")}}},')
            lines.append(f"  author = {{{author_str}}},")
            lines.append(f'  journal = {{{p.get("journal", "")}}},')
            lines.append(f"  year = {{{year}}},")
            if doi:
                lines.append(f"  doi = {{{doi}}},")
            lines.append("}")
            lines.append("")
        return {"format": "bibtex", "content": "\n".join(lines), "count": len(papers)}

    else:  # csv
        import csv
        import io
        buf = io.StringIO()
        writer = csv.writer(buf)
        writer.writerow(["title", "authors", "journal", "year", "doi", "abstract"])
        for p in papers:
            authors = p.get("authors", [])
            if isinstance(authors, list):
                author_str = "; ".join(
                    a.get("name", a) if isinstance(a, dict) else str(a)
                    for a in authors
                )
            else:
                author_str = str(authors)
            year = str(p.get("published_date", ""))[:4] if p.get("published_date") else ""
            writer.writerow([
                p.get("title", ""),
                author_str,
                p.get("journal", ""),
                year,
                p.get("doi", ""),
                (p.get("abstract", "") or "")[:200],
            ])
        return {"format": "csv", "content": buf.getvalue(), "count": len(papers)}


# ---------------------------------------------------------------------------
# Watchlists
# ---------------------------------------------------------------------------

@app.get("/workspace/watchlists")
def list_watchlists(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id, name, watch_type, watch_value, last_checked_at, new_count, created_at FROM watchlists WHERE user_id = %s ORDER BY created_at DESC",
        (current_user["sub"],),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]
    release_db(conn)
    return {"watchlists": rows}


@app.post("/workspace/watchlists", status_code=201)
def create_watchlist(request: WatchlistCreate, current_user: dict = Depends(get_current_user)):
    if request.watch_type not in ("entity", "query", "author"):
        raise HTTPException(status_code=400, detail="watch_type must be entity, query, or author")
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "INSERT INTO watchlists (user_id, name, watch_type, watch_value) VALUES (%s, %s, %s, %s) RETURNING id, name, watch_type, watch_value, created_at",
        (current_user["sub"], request.name, request.watch_type, request.watch_value),
    )
    row = _jsonify_row(dict(cur.fetchone()))
    conn.commit()
    release_db(conn)
    return row


@app.delete("/workspace/watchlists/{watchlist_id}", status_code=204)
def delete_watchlist(watchlist_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM watchlists WHERE id = %s AND user_id = %s", (watchlist_id, current_user["sub"]))
    conn.commit()
    release_db(conn)


# ---------------------------------------------------------------------------
# Workspaces
# ---------------------------------------------------------------------------

@app.get("/workspace/workspaces")
def list_workspaces(current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT id, name, description, state, is_default, created_at, updated_at FROM decoded_workspaces WHERE user_id = %s ORDER BY is_default DESC, created_at DESC",
        (current_user["sub"],),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]
    release_db(conn)
    return {"workspaces": rows}


@app.post("/workspace/workspaces", status_code=201)
def create_workspace(request: WorkspaceCreate, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    if request.is_default:
        # Unset existing default
        cur.execute("UPDATE decoded_workspaces SET is_default = false WHERE user_id = %s", (current_user["sub"],))
    cur.execute(
        "INSERT INTO decoded_workspaces (user_id, name, description, state, is_default) VALUES (%s, %s, %s, %s, %s) RETURNING id, name, description, state, is_default, created_at",
        (current_user["sub"], request.name, request.description, json.dumps(request.state), request.is_default),
    )
    row = _jsonify_row(dict(cur.fetchone()))
    conn.commit()
    release_db(conn)
    return row


@app.put("/workspace/workspaces/{workspace_id}")
def update_workspace(
    workspace_id: str,
    request: WorkspaceUpdate,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    # Verify ownership
    cur.execute("SELECT id FROM decoded_workspaces WHERE id = %s AND user_id = %s", (workspace_id, current_user["sub"]))
    if not cur.fetchone():
        release_db(conn)
        raise HTTPException(status_code=404, detail="Workspace not found")
    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.description is not None:
        updates["description"] = request.description
    if request.state is not None:
        updates["state"] = json.dumps(request.state)
    if not updates:
        release_db(conn)
        return {"status": "no changes"}
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [workspace_id]
    cur.execute(
        f"UPDATE decoded_workspaces SET {set_clause} WHERE id = %s RETURNING id, name, description, state, is_default, updated_at",
        values,
    )
    row = _jsonify_row(dict(cur.fetchone()))
    conn.commit()
    release_db(conn)
    return row


# ---------------------------------------------------------------------------
# v1/stats — comprehensive stats endpoint (Step 8)
# ---------------------------------------------------------------------------

@app.get("/v1/stats")
def stats_v1():
    """Comprehensive stats including entities, claims, graph nodes, relationships."""
    # Check Redis cache first (60s TTL)
    if _redis:
        cached = _redis.get("decoded:stats_v1")
        if cached:
            return json.loads(cached)

    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    cur.execute("SELECT status, count(*) as n FROM raw_papers GROUP BY status ORDER BY n DESC")
    paper_stats = {r["status"]: r["n"] for r in cur.fetchall()}

    cur.execute("SELECT count(*) as n FROM raw_papers")
    total_papers = cur.fetchone()["n"]

    cur.execute("SELECT count(*) as n FROM extraction_results")
    total_extractions = cur.fetchone()["n"]

    cur.execute("SELECT count(*) as n FROM discovered_connections WHERE connection_type != 'replicates'")
    total_connections = cur.fetchone()["n"]

    cur.execute("SELECT count(*) as n FROM paper_critiques")
    total_critiques = cur.fetchone()["n"]

    cur.execute("SELECT count(*) as n FROM paper_critiques WHERE overall_quality = 'high'")
    high_quality_critiques = cur.fetchone()["n"]

    # Count entities from extraction_results JSONB
    cur.execute("""
        SELECT COALESCE(SUM(jsonb_array_length(entities::jsonb)), 0) as total_entities
        FROM extraction_results
        WHERE entities IS NOT NULL AND entities != 'null' AND entities::text LIKE '[%'
    """)
    total_entities = int(cur.fetchone()["total_entities"] or 0)

    # Count claims from dedicated table (fallback to JSONB count)
    cur.execute("SELECT count(*) as n FROM claims")
    claims_row = cur.fetchone()
    total_claims = int(claims_row["n"]) if claims_row and claims_row["n"] else 0

    # Convergence zones and field gaps
    cur.execute("SELECT count(*) as n FROM convergence_zones")
    convergence_zones = cur.fetchone()["n"]

    cur.execute("SELECT count(*) as n FROM field_gaps")
    field_gaps_count = cur.fetchone()["n"]

    # Data quality coverage
    cur.execute("SELECT count(*) as n FROM raw_papers WHERE data_source LIKE 'full_text%'")
    full_text_count = cur.fetchone()["n"]
    full_text_pct = round(full_text_count / max(total_papers, 1) * 100, 1)

    cur.execute("SELECT count(*) as n FROM paper_critiques WHERE brief_confidence = 'high'")
    high_confidence_briefs = cur.fetchone()["n"]

    cur.execute("SELECT connection_type, count(*) as n FROM discovered_connections WHERE connection_type != 'replicates' GROUP BY connection_type ORDER BY n DESC")
    connection_types = {r["connection_type"]: r["n"] for r in cur.fetchall()}

    # Try to get Neo4j counts
    graph_nodes = 0
    graph_relationships = 0
    try:
        from neo4j import GraphDatabase
        neo4j_uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
        neo4j_user = os.environ.get("NEO4J_USER", "neo4j")
        neo4j_pw = os.environ.get("NEO4J_PASSWORD", "")
        driver = GraphDatabase.driver(neo4j_uri, auth=(neo4j_user, neo4j_pw))
        with driver.session() as s:
            graph_nodes = s.run("MATCH (n) RETURN count(n) as c").single()["c"]
            graph_relationships = s.run("MATCH ()-[r]->() RETURN count(r) as c").single()["c"]
        driver.close()
    except Exception:
        pass

    release_db(conn)
    result = {
        "papers": {"total": total_papers, "by_status": paper_stats},
        "extractions": total_extractions,
        "connections": {"total": total_connections, "by_type": connection_types},
        "critiques": total_critiques,
        "high_quality_critiques": high_quality_critiques,
        "entities": total_entities,
        "claims": total_claims,
        "convergence_zones": convergence_zones,
        "field_gaps": field_gaps_count,
        "graph": {"nodes": graph_nodes, "relationships": graph_relationships},
        "data_quality": {
            "full_text_papers": full_text_count,
            "full_text_pct": full_text_pct,
            "high_confidence_briefs": high_confidence_briefs,
        },
    }
    # Cache for 60 seconds
    if _redis:
        try:
            _redis.setex("decoded:stats_v1", 60, json.dumps(result))
        except Exception:
            pass
    return result


# ---------------------------------------------------------------------------
# v1/graph — graph data endpoints for visualization (Step 3)
# ---------------------------------------------------------------------------

@app.get("/v1/graph/overview")
def graph_overview(limit: int = Query(200, le=500)):
    """Top most-connected papers and their connections for force-graph visualization."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get top papers by connection count
    cur.execute(
        """
        SELECT p.id, p.title, p.journal, p.source,
               COUNT(DISTINCT dc.id) as connection_count
        FROM raw_papers p
        JOIN discovered_connections dc ON dc.paper_a_id = p.id OR dc.paper_b_id = p.id
        WHERE dc.connection_type != 'replicates'
        GROUP BY p.id, p.title, p.journal, p.source
        ORDER BY connection_count DESC
        LIMIT %s
        """,
        (limit,),
    )
    papers = [dict(r) for r in cur.fetchall()]
    paper_ids = {str(p["id"]) for p in papers}

    # Get connections between these papers
    if paper_ids:
        placeholders = ",".join(["%s"] * len(paper_ids))
        cur.execute(
            f"""
            SELECT id, paper_a_id, paper_b_id, connection_type, confidence, novelty_score
            FROM discovered_connections
            WHERE paper_a_id IN ({placeholders})
              AND paper_b_id IN ({placeholders})
              AND connection_type != 'replicates'
            ORDER BY confidence DESC
            LIMIT 2000
            """,
            (*paper_ids, *paper_ids),
        )
        connections = [dict(r) for r in cur.fetchall()]
    else:
        connections = []

    release_db(conn)

    nodes = [
        {
            "id": str(p["id"]),
            "label": (p["title"] or "")[:60],
            "title": p["title"],
            "journal": p["journal"],
            "source": p["source"],
            "val": min(p["connection_count"], 20),
        }
        for p in papers
    ]
    links = [
        {
            "source": str(c["paper_a_id"]),
            "target": str(c["paper_b_id"]),
            "type": c["connection_type"],
            "confidence": float(c["confidence"] or 0),
        }
        for c in connections
        if str(c["paper_a_id"]) in paper_ids and str(c["paper_b_id"]) in paper_ids
    ]
    return {"nodes": nodes, "links": links, "node_count": len(nodes), "link_count": len(links)}


@app.get("/v1/graph/neighborhood/{paper_id}")
def graph_neighborhood(paper_id: str, hops: int = Query(2, le=3)):
    """Papers within N hops of a paper node."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get direct connections first
    cur.execute(
        """
        SELECT dc.paper_a_id, dc.paper_b_id, dc.connection_type, dc.confidence,
               p_a.title as title_a, p_b.title as title_b,
               p_a.journal as journal_a, p_b.journal as journal_b,
               p_a.source as source_a, p_b.source as source_b
        FROM discovered_connections dc
        JOIN raw_papers p_a ON p_a.id = dc.paper_a_id
        JOIN raw_papers p_b ON p_b.id = dc.paper_b_id
        WHERE (dc.paper_a_id = %s OR dc.paper_b_id = %s)
          AND dc.connection_type != 'replicates'
        ORDER BY dc.confidence DESC
        LIMIT 100
        """,
        (paper_id, paper_id),
    )
    direct = [dict(r) for r in cur.fetchall()]

    # Collect all neighbor IDs for hop 2
    neighbor_ids = set()
    for row in direct:
        neighbor_ids.add(str(row["paper_a_id"]))
        neighbor_ids.add(str(row["paper_b_id"]))
    neighbor_ids.discard(str(paper_id))

    hop2_connections = []
    if hops >= 2 and neighbor_ids:
        placeholders = ",".join(["%s"] * len(neighbor_ids))
        cur.execute(
            f"""
            SELECT dc.paper_a_id, dc.paper_b_id, dc.connection_type, dc.confidence,
                   p_a.title as title_a, p_b.title as title_b,
                   p_a.journal as journal_a, p_b.journal as journal_b,
                   p_a.source as source_a, p_b.source as source_b
            FROM discovered_connections dc
            JOIN raw_papers p_a ON p_a.id = dc.paper_a_id
            JOIN raw_papers p_b ON p_b.id = dc.paper_b_id
            WHERE (dc.paper_a_id IN ({placeholders}) OR dc.paper_b_id IN ({placeholders}))
              AND dc.connection_type != 'replicates'
            ORDER BY dc.confidence DESC
            LIMIT 200
            """,
            (*neighbor_ids, *neighbor_ids),
        )
        hop2_connections = [dict(r) for r in cur.fetchall()]

    release_db(conn)

    all_connections = direct + hop2_connections
    node_map = {}
    for row in all_connections:
        for pid, title, journal, source in [
            (str(row["paper_a_id"]), row["title_a"], row["journal_a"], row["source_a"]),
            (str(row["paper_b_id"]), row["title_b"], row["journal_b"], row["source_b"]),
        ]:
            if pid not in node_map:
                node_map[pid] = {"id": pid, "title": title, "journal": journal, "source": source, "val": 5}

    # Center node gets bigger
    if str(paper_id) in node_map:
        node_map[str(paper_id)]["val"] = 15
        node_map[str(paper_id)]["center"] = True

    links = [
        {
            "source": str(r["paper_a_id"]),
            "target": str(r["paper_b_id"]),
            "type": r["connection_type"],
            "confidence": float(r["confidence"] or 0),
        }
        for r in all_connections
    ]
    return {"nodes": list(node_map.values()), "links": links}


@app.get("/v1/graph/cluster/{discipline}")
def graph_cluster(discipline: str):
    """Papers from a specific source/journal cluster."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT p.id, p.title, p.journal, p.source,
               COUNT(DISTINCT dc.id) as connection_count
        FROM raw_papers p
        LEFT JOIN discovered_connections dc ON dc.paper_a_id = p.id OR dc.paper_b_id = p.id
        WHERE p.source = %s OR p.journal ILIKE %s
        GROUP BY p.id, p.title, p.journal, p.source
        ORDER BY connection_count DESC
        LIMIT 100
        """,
        (discipline, f"%{discipline}%"),
    )
    papers = [dict(r) for r in cur.fetchall()]
    paper_ids = {str(p["id"]) for p in papers}

    links = []
    if paper_ids:
        placeholders = ",".join(["%s"] * len(paper_ids))
        cur.execute(
            f"""
            SELECT paper_a_id, paper_b_id, connection_type, confidence
            FROM discovered_connections
            WHERE paper_a_id IN ({placeholders}) AND paper_b_id IN ({placeholders})
              AND connection_type != 'replicates'
            """,
            (*paper_ids, *paper_ids),
        )
        links = [
            {"source": str(r["paper_a_id"]), "target": str(r["paper_b_id"]),
             "type": r["connection_type"], "confidence": float(r["confidence"] or 0)}
            for r in cur.fetchall()
        ]

    release_db(conn)
    nodes = [
        {"id": str(p["id"]), "title": p["title"], "journal": p["journal"],
         "source": p["source"], "val": min(int(p["connection_count"] or 1), 20)}
        for p in papers
    ]
    return {"nodes": nodes, "links": links}


# ---------------------------------------------------------------------------
# v1/papers/analyze — on-demand DOI analysis with job tracking (Step 9)
# ---------------------------------------------------------------------------

import uuid as _uuid
import time as _time

_ANALYZE_JOB_PREFIX = "decoded:analyze_job:"


def _set_analyze_job(job_id: str, data: dict):
    """Store analyze job in Redis with 24h TTL."""
    if _redis:
        _redis.setex(f"{_ANALYZE_JOB_PREFIX}{job_id}", 86400, json.dumps(data))


def _get_analyze_job(job_id: str) -> dict | None:
    """Retrieve analyze job from Redis."""
    if _redis:
        raw = _redis.get(f"{_ANALYZE_JOB_PREFIX}{job_id}")
        if raw:
            return json.loads(raw)
    return None


class AnalyzeJobRequest(BaseModel):
    doi: str
    priority: int = 1


@app.post("/v1/papers/analyze")
async def analyze_doi_v1(request: AnalyzeJobRequest, background_tasks: BackgroundTasks):
    """Queue DOI analysis and return a job_id for polling."""
    job_id = str(_uuid.uuid4())
    _set_analyze_job(job_id, {
        "job_id": job_id,
        "doi": request.doi,
        "status": "queued",
        "stage": None,
        "paper_id": None,
        "error": None,
        "created_at": _time.time(),
    })
    background_tasks.add_task(_run_doi_analysis_tracked, job_id, request.doi, request.priority)
    return {"job_id": job_id, "doi": request.doi, "status": "queued"}


@app.get("/v1/papers/analyze/{job_id}")
def get_analyze_job(job_id: str):
    """Poll status of a DOI analysis job."""
    job = _get_analyze_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


def _run_doi_analysis_tracked(job_id: str, doi: str, priority: int = 1) -> None:
    """Background task with stage tracking."""
    def _update(stage: str, status: str = "running", paper_id=None, error=None):
        data = _get_analyze_job(job_id)
        if data:
            data.update({"stage": stage, "status": status})
            if paper_id:
                data["paper_id"] = paper_id
            if error:
                data["error"] = error
            _set_analyze_job(job_id, data)

    try:
        _update("fetching")
        from decoded.api.analysis_worker import AnalysisWorker
        worker = AnalysisWorker()

        # Check if already in DB
        conn = get_db()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute("SELECT id, status FROM raw_papers WHERE doi = %s LIMIT 1", (doi,))
        existing = cur.fetchone()
        release_db(conn)

        if existing:
            _update("fetching", paper_id=str(existing["id"]))
        else:
            _update("fetching")

        _update("extracting")
        result = worker.analyze_doi(doi, priority=priority)
        if not result:
            _update("error", status="failed", error="Analysis returned no result")
            return
        if result.get("status") == "error":
            _update("error", status="failed", error=result.get("message", "Unknown error"))
            return

        paper_id = result.get("paper_id")
        # Store rich report data in job for frontend to read
        data = _get_analyze_job(job_id) or {}
        data["connections"] = result.get("connections", [])
        data["connection_count"] = result.get("connection_count", 0)
        data["brief"] = result.get("brief")
        _set_analyze_job(job_id, data)
        _update("done", status="complete", paper_id=paper_id)
    except Exception as exc:
        logger.error("Tracked DOI analysis failed for %s: %s", doi, exc, exc_info=True)
        _update("error", status="failed", error=str(exc)[:200])


# ---------------------------------------------------------------------------
# v1/convergences — convergence zones with convergent claims (Step 7)
# ---------------------------------------------------------------------------

@app.get("/v1/convergences")
def get_convergences_v1(
    min_confidence: float = Query(0.7),
    limit: int = Query(20, le=100),
):
    """Convergence zones with convergent claim text from shared entities."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT p.id, p.title, p.doi, p.journal,
               COUNT(DISTINCT dc.id) as connection_count,
               AVG(dc.confidence) as avg_confidence,
               ARRAY_AGG(DISTINCT dc.connection_type) as connection_types,
               ARRAY_AGG(DISTINCT dc.description ORDER BY dc.description) as descriptions
        FROM raw_papers p
        JOIN discovered_connections dc
            ON dc.paper_a_id = p.id OR dc.paper_b_id = p.id
        WHERE dc.confidence >= %s AND dc.connection_type != 'replicates'
        GROUP BY p.id, p.title, p.doi, p.journal
        HAVING COUNT(DISTINCT dc.id) >= 2
        ORDER BY connection_count DESC, avg_confidence DESC
        LIMIT %s
        """,
        (min_confidence, limit),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]

    # Enrich with convergent claim text
    for row in rows:
        paper_id = row["id"]
        # Get papers connected to this one
        cur.execute(
            """
            SELECT DISTINCT
                CASE WHEN dc.paper_a_id = %s THEN dc.paper_b_id ELSE dc.paper_a_id END as other_id,
                dc.connection_type, dc.description, dc.confidence
            FROM discovered_connections dc
            WHERE (dc.paper_a_id = %s OR dc.paper_b_id = %s)
              AND dc.confidence >= %s
              AND dc.connection_type != 'replicates'
            ORDER BY dc.confidence DESC
            LIMIT 5
            """,
            (paper_id, paper_id, paper_id, min_confidence),
        )
        connected = [dict(r) for r in cur.fetchall()]
        row["connected_papers"] = connected

        # Find shared claims/entities as convergent claim
        if connected:
            other_ids = [str(r["other_id"]) for r in connected]
            # Get key findings from center paper
            cur.execute(
                "SELECT key_findings FROM extraction_results WHERE paper_id = %s LIMIT 1",
                (str(paper_id),),
            )
            ef = cur.fetchone()
            row["convergent_claim"] = None
            if ef and ef["key_findings"]:
                kf = ef["key_findings"]
                if isinstance(kf, str):
                    try:
                        kf = json.loads(kf)
                    except Exception:
                        kf = kf
                if isinstance(kf, list) and kf:
                    row["convergent_claim"] = kf[0] if isinstance(kf[0], str) else str(kf[0])
                elif isinstance(kf, str) and kf:
                    row["convergent_claim"] = kf[:200]

    release_db(conn)
    return {"convergences": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# v1/papers/{id}/missed-citations — papers connected but not cited
# ---------------------------------------------------------------------------

@app.get("/v1/papers/{paper_id}/missed-citations")
def get_missed_citations(paper_id: str):
    """Papers connected in the graph but not in each other's reference lists."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Get connected papers
    cur.execute(
        """
        SELECT
            CASE WHEN dc.paper_a_id = %s THEN dc.paper_b_id ELSE dc.paper_a_id END as other_id,
            dc.connection_type,
            dc.description,
            dc.confidence,
            dc.novelty_score
        FROM discovered_connections dc
        WHERE (dc.paper_a_id = %s OR dc.paper_b_id = %s)
          AND dc.connection_type != 'replicates'
        ORDER BY dc.novelty_score DESC NULLS LAST, dc.confidence DESC
        LIMIT 50
        """,
        (paper_id, paper_id, paper_id),
    )
    connected = {str(r["other_id"]): dict(r) for r in cur.fetchall()}

    if not connected:
        release_db(conn)
        return {"missed_citations": []}

    # Get reference DOIs for the source paper
    cur.execute(
        "SELECT references_list FROM raw_papers WHERE id = %s LIMIT 1",
        (paper_id,),
    )
    row = cur.fetchone()
    refs_raw = row["references_list"] if row else None
    cited_dois = set()
    if refs_raw:
        try:
            refs = refs_raw if isinstance(refs_raw, list) else __import__('json').loads(refs_raw)
            for r in refs:
                if isinstance(r, dict) and r.get("doi"):
                    cited_dois.add(r["doi"].lower().strip())
        except Exception:
            pass

    # Get metadata for connected papers, filter out already-cited ones
    other_ids = list(connected.keys())
    placeholders = ",".join(["%s"] * len(other_ids))
    cur.execute(
        f"""
        SELECT id, title, doi, journal, pub_year
        FROM raw_papers
        WHERE id IN ({placeholders})
        """,
        other_ids,
    )
    papers = {str(r["id"]): dict(r) for r in cur.fetchall()}

    missed = []
    for oid, conn_data in connected.items():
        paper = papers.get(oid)
        if not paper:
            continue
        doi = (paper.get("doi") or "").lower().strip()
        if doi and doi in cited_dois:
            continue  # Already cited — not a missed citation
        missed.append({
            "id": oid,
            "title": paper.get("title"),
            "doi": paper.get("doi"),
            "journal": paper.get("journal"),
            "year": paper.get("pub_year"),
            "connection_type": conn_data["connection_type"],
            "description": conn_data["description"],
            "confidence": float(conn_data["confidence"] or 0),
            "novelty_score": float(conn_data["novelty_score"] or 0) if conn_data["novelty_score"] else None,
        })

    missed.sort(key=lambda x: (-(x["novelty_score"] or 0), -(x["confidence"] or 0)))
    release_db(conn)
    return {"missed_citations": missed[:20], "total": len(missed)}


# ---------------------------------------------------------------------------
# v1/gaps — structured field gaps from table (falls back to computed gaps)
# ---------------------------------------------------------------------------

@app.get("/v1/gaps")
def get_structured_gaps(
    discipline: str | None = Query(None),
    importance: str | None = Query(None),
    limit: int = Query(50, le=100),
):
    """Structured field gaps discovered from graph negative space."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    where = ["1=1"]
    params: list = []
    if discipline:
        where.append("discipline = %s")
        params.append(discipline)
    if importance:
        where.append("importance = %s")
        params.append(importance)
    params.append(limit)

    cur.execute(
        f"""
        SELECT * FROM field_gaps
        WHERE {" AND ".join(where)}
        ORDER BY
            CASE importance WHEN 'high' THEN 1 WHEN 'medium' THEN 2 ELSE 3 END,
            discovered_at DESC
        LIMIT %s
        """,
        params,
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]
    release_db(conn)
    return {"gaps": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# Bridge result caching — store/retrieve bridge query results
# ---------------------------------------------------------------------------

@app.get("/v1/bridge/{concept_a}/{concept_b}")
def get_cached_bridge(concept_a: str, concept_b: str):
    """Retrieve a cached bridge result if it exists."""
    a, b = sorted([concept_a.lower().strip(), concept_b.lower().strip()])
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        "SELECT * FROM bridge_results WHERE concept_a = %s AND concept_b = %s",
        (a, b),
    )
    row = cur.fetchone()
    if row:
        cur.execute(
            "UPDATE bridge_results SET query_count = query_count + 1 WHERE id = %s",
            (str(row["id"]),),
        )
        conn.commit()
    release_db(conn)
    if not row:
        raise HTTPException(status_code=404, detail="No cached bridge result")
    return _jsonify_row(dict(row))


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("decoded.api.main:app", host="0.0.0.0", port=8000, reload=True)
