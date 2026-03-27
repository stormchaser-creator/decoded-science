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
from fastapi import FastAPI, HTTPException, Query, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

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

    if status:
        where_clauses.append("p.status = %s")
        params.append(status)
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
        WHERE dc.paper_a_id = %s OR dc.paper_b_id = %s
        ORDER BY dc.confidence DESC
        """,
        (paper_id, paper_id),
    )
    rows = [_jsonify_row(dict(r)) for r in cur.fetchall()]
    conn.close()
    return {"paper_id": paper_id, "connections": rows, "count": len(rows)}


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

    where_clauses = ["dc.confidence >= %s"]
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
        WHERE dc.confidence >= %s
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
    return {
        "concept_a": result["concept_a"],
        "concept_b": result["concept_b"],
        "graph_paths_found": len(result.get("graph_paths", [])),
        "papers_a_count": len(result.get("papers_a", [])),
        "papers_b_count": len(result.get("papers_b", [])),
        "similar_papers": result.get("similar_papers", [])[:5],
        "hypothesis": result.get("hypothesis", {}).get("hypothesis") if result.get("hypothesis") else None,
        "cost_usd": result.get("hypothesis", {}).get("cost_usd", 0) if result.get("hypothesis") else 0,
    }


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("decoded.api.main:app", host="0.0.0.0", port=8000, reload=True)
