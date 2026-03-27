"""On-demand DOI analysis worker.

Given a DOI:
1. Fetch paper metadata from PubMed/CrossRef
2. Fetch full text if available
3. Run LLM extraction
4. Add to Neo4j graph
5. Run connection discovery against existing papers
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=False)

logger = logging.getLogger(__name__)


def get_db_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    psycopg2.extras.register_uuid(conn)
    return conn


class AnalysisWorker:
    """On-demand analysis pipeline for a single DOI."""

    def analyze_doi(self, doi: str, priority: int = 0) -> dict:
        """Full pipeline: fetch → extract → graph → connect.

        Returns a summary of what was done.
        """
        conn = get_db_conn()
        cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

        # Check if already in DB
        cur.execute(
            "SELECT id, status FROM raw_papers WHERE doi = %s LIMIT 1",
            (doi,),
        )
        existing = cur.fetchone()
        if existing:
            paper_id = str(existing["id"])
            logger.info("DOI %s already in DB as paper %s (status: %s)", doi, paper_id, existing["status"])
        else:
            paper_id = self._fetch_and_store(conn, doi)

        if not paper_id:
            return {"status": "error", "message": f"Could not fetch DOI: {doi}"}

        result = {"doi": doi, "paper_id": paper_id, "steps": []}

        # Extract if not already done
        cur.execute("SELECT id FROM extraction_results WHERE paper_id = %s", (paper_id,))
        if not cur.fetchone():
            try:
                self._extract(conn, paper_id)
                result["steps"].append("extracted")
            except Exception as exc:
                logger.error("Extraction failed for %s: %s", paper_id, exc)
                result["steps"].append(f"extraction_error: {exc}")

        # Add to graph
        try:
            self._add_to_graph(conn, paper_id)
            result["steps"].append("graph_updated")
        except Exception as exc:
            logger.error("Graph update failed for %s: %s", paper_id, exc)

        # Quick connection discovery against existing papers
        try:
            n_connections = self._discover_connections(conn, paper_id)
            result["steps"].append(f"connections_found: {n_connections}")
        except Exception as exc:
            logger.error("Connection discovery failed: %s", exc)

        conn.close()
        result["status"] = "complete"
        return result

    def _fetch_and_store(self, conn, doi: str) -> str | None:
        """Fetch paper metadata from PubMed via DOI and store it."""
        import httpx
        import json
        from uuid import uuid4

        # Try CrossRef for metadata
        try:
            url = f"https://api.crossref.org/works/{doi}"
            resp = httpx.get(url, timeout=15, headers={"User-Agent": "Decoded/0.1 mailto:research@decoded.ai"})
            if resp.status_code == 200:
                data = resp.json()["message"]
                title_parts = data.get("title", [])
                title = title_parts[0] if title_parts else "Unknown"
                authors = []
                for a in data.get("author", []):
                    name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                    if name:
                        authors.append(name)
                abstract = ""
                if "abstract" in data:
                    import re
                    abstract = re.sub(r"<[^>]+>", "", data["abstract"]).strip()
                journal_items = data.get("container-title", [])
                journal = journal_items[0] if journal_items else None
                pub_date = None
                if "published" in data:
                    parts = data["published"].get("date-parts", [[]])[0]
                    if parts:
                        from datetime import date
                        pub_date = date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)

                paper_id = str(uuid4())
                cur = conn.cursor()
                cur.execute(
                    """
                    INSERT INTO raw_papers
                        (id, source, external_id, title, abstract, authors, journal,
                         doi, published_date, status, raw_metadata, created_at, updated_at)
                    VALUES (%s, 'crossref', %s, %s, %s, %s, %s, %s, %s, 'fetched', %s, NOW(), NOW())
                    ON CONFLICT (source, external_id) DO UPDATE SET
                        title = EXCLUDED.title,
                        updated_at = NOW()
                    RETURNING id
                    """,
                    (
                        paper_id,
                        doi,
                        title,
                        abstract,
                        json.dumps(authors),
                        journal,
                        doi,
                        pub_date,
                        json.dumps({"crossref": True}),
                    ),
                )
                result = cur.fetchone()
                conn.commit()
                logger.info("Fetched DOI %s from CrossRef: %s", doi, title[:60])
                return str(result[0]) if result else paper_id
        except Exception as exc:
            logger.warning("CrossRef fetch failed for %s: %s", doi, exc)

        return None

    def _extract(self, conn, paper_id: str) -> None:
        """Run LLM extraction on the paper."""
        from decoded.extract.worker import ExtractionWorker
        worker = ExtractionWorker(limit=1, paper_id=paper_id)
        worker.run()

    def _add_to_graph(self, conn, paper_id: str) -> None:
        """Add paper to Neo4j graph."""
        from decoded.graph.worker import GraphWorker
        worker = GraphWorker(paper_id=paper_id, sync_connections=False)
        worker.run()

    def _discover_connections(self, conn, paper_id: str) -> int:
        """Quick connection discovery for this paper against existing papers."""
        from decoded.connect.graph_discovery import GraphDiscovery
        gd = GraphDiscovery()
        shared = gd.find_shared_entities(min_shared=1, limit=10)
        gd.close()
        return len([c for c in shared if c.get("paper_a_id") == paper_id or c.get("paper_b_id") == paper_id])
