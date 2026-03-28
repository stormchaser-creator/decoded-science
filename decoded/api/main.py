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

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---------------------------------------------------------------------------
# DB connection pool (simple per-request)
# ---------------------------------------------------------------------------

def get_db():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    psycopg2.extras.register_uuid(conn)
    return conn


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
    email: str
    name: str
    password: str


class LoginRequest(BaseModel):
    email: str
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
# Health
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    try:
        conn = get_db()
        cur = conn.cursor()
        cur.execute("SELECT 1")
        conn.close()
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

    conn.close()
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

    conn.close()
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
    conn.close()
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
    conn.close()
    return {"paper_id": paper_id, "connections": rows, "count": len(rows)}


@app.get("/critiques")
def list_critiques(limit: int = Query(20, le=100), skip: int = Query(0)):
    """List all intelligence briefs (paper critiques) with paper metadata."""
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT pc.id, pc.paper_id, pc.overall_quality, pc.brief, pc.strengths,
               pc.weaknesses, pc.connections_summary, pc.confidence_score,
               pc.created_at, p.title as paper_title, p.journal, p.published_date
        FROM paper_critiques pc
        JOIN raw_papers p ON p.id = pc.paper_id
        ORDER BY pc.created_at DESC
        LIMIT %s OFFSET %s
        """,
        (limit, skip),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]
    cur.execute("SELECT COUNT(*) as n FROM paper_critiques")
    total = cur.fetchone()["n"]
    conn.close()
    return {"critiques": rows, "total": total, "count": len(rows)}


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
    conn.close()
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
    conn.close()
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

    conn.close()
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
    conn.close()
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
    conn.close()
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
    search_term = f"%{q}%"
    cur.execute(
        """
        SELECT p.id, p.title, p.abstract, p.authors, p.journal,
               p.doi, p.published_date, p.status,
               COUNT(DISTINCT dc.id) as connection_count
        FROM raw_papers p
        LEFT JOIN discovered_connections dc ON dc.paper_a_id = p.id OR dc.paper_b_id = p.id
        WHERE p.title ILIKE %s
           OR p.abstract ILIKE %s
        GROUP BY p.id, p.title, p.abstract, p.authors, p.journal,
                 p.doi, p.published_date, p.status
        ORDER BY connection_count DESC, p.published_date DESC NULLS LAST
        LIMIT %s
        """,
        (search_term, search_term, limit),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]
    conn.close()
    return {"query": q, "results": rows, "count": len(rows)}


# ---------------------------------------------------------------------------
# On-demand analysis
# ---------------------------------------------------------------------------

@app.post("/analyze")
async def analyze_doi(request: AnalyzeRequest, background_tasks: BackgroundTasks):
    """Trigger on-demand analysis of a paper by DOI."""
    background_tasks.add_task(_run_doi_analysis, request.doi, request.priority)
    return {
        "status": "queued",
        "doi": request.doi,
        "message": "Analysis started in background. Check /papers or /search for results.",
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
def bridge_query(request: BridgeRequest):
    """On-demand bridge query: find/build connection between two concepts."""
    from decoded.connect.worker import BridgeQueryWorker
    worker = BridgeQueryWorker()
    result = worker.query(
        concept_a=request.concept_a,
        concept_b=request.concept_b,
        max_hops=request.max_hops,
    )
    # Serialize for JSON response
    graph_paths = result.get("graph_paths", [])
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
        "hypothesis": result.get("hypothesis", {}).get("hypothesis") if result.get("hypothesis") else None,
        "cost_usd": result.get("hypothesis", {}).get("cost_usd", 0) if result.get("hypothesis") else 0,
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
    conn.close()
    return {"total_entries": total, "breakdown": rows}


# ---------------------------------------------------------------------------
# Auth helpers
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
# Auth endpoints
# ---------------------------------------------------------------------------

@app.post("/auth/register", status_code=201)
def register(request: RegisterRequest):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id FROM decoded_users WHERE email = %s", (request.email,))
    if cur.fetchone():
        conn.close()
        raise HTTPException(status_code=409, detail="Email already registered")
    pw_hash = hash_password(request.password)
    cur.execute(
        "INSERT INTO decoded_users (email, name, password_hash) VALUES (%s, %s, %s) RETURNING id, email, name, role, created_at",
        (request.email, request.name, pw_hash),
    )
    user = dict(cur.fetchone())
    conn.commit()
    conn.close()
    user["created_at"] = user["created_at"].isoformat() if user.get("created_at") else None
    token = create_access_token(str(user["id"]), user["email"])
    return {"user": user, "token": token}


@app.post("/auth/login")
def login(request: LoginRequest):
    conn = get_db()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute("SELECT id, email, name, role, password_hash FROM decoded_users WHERE email = %s", (request.email,))
    row = cur.fetchone()
    conn.close()
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
    conn.close()
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
    conn.close()
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
    conn.close()
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
    conn.close()


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
    conn.close()
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
    conn.close()
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
        conn.close()
        raise HTTPException(status_code=404, detail="Collection not found")
    cur.execute(
        "INSERT INTO collection_papers (collection_id, paper_id, notes) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
        (collection_id, request.paper_id, request.notes),
    )
    conn.commit()
    conn.close()
    return {"status": "added"}


@app.delete("/workspace/collections/{collection_id}/papers/{paper_id}", status_code=204)
def remove_paper_from_collection(
    collection_id: str,
    paper_id: str,
    current_user: dict = Depends(get_current_user),
):
    conn = get_db()
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM collection_papers WHERE collection_id = %s AND paper_id = %s",
        (collection_id, paper_id),
    )
    conn.commit()
    conn.close()


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
    conn.close()

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
    conn.close()
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
    conn.close()
    return row


@app.delete("/workspace/watchlists/{watchlist_id}", status_code=204)
def delete_watchlist(watchlist_id: str, current_user: dict = Depends(get_current_user)):
    conn = get_db()
    cur = conn.cursor()
    cur.execute("DELETE FROM watchlists WHERE id = %s AND user_id = %s", (watchlist_id, current_user["sub"]))
    conn.commit()
    conn.close()


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
    conn.close()
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
    conn.close()
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
        conn.close()
        raise HTTPException(status_code=404, detail="Workspace not found")
    updates = {}
    if request.name is not None:
        updates["name"] = request.name
    if request.description is not None:
        updates["description"] = request.description
    if request.state is not None:
        updates["state"] = json.dumps(request.state)
    if not updates:
        conn.close()
        return {"status": "no changes"}
    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [workspace_id]
    cur.execute(
        f"UPDATE decoded_workspaces SET {set_clause} WHERE id = %s RETURNING id, name, description, state, is_default, updated_at",
        values,
    )
    row = _jsonify_row(dict(cur.fetchone()))
    conn.commit()
    conn.close()
    return row


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("decoded.api.main:app", host="0.0.0.0", port=8000, reload=True)
