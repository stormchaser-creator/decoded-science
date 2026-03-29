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
            "SELECT id, status, abstract, full_text, sections FROM raw_papers WHERE doi = %s LIMIT 1",
            (doi,),
        )
        existing = cur.fetchone()
        if existing:
            paper_id = str(existing["id"])
            has_content = bool(
                existing["abstract"] or existing["full_text"] or
                (existing["sections"] and existing["sections"] != {})
            )
            if has_content:
                logger.info("DOI %s already in DB with content (status: %s)", doi, existing["status"])
            else:
                # Paper is in DB but has no content — re-run fetch to try scraping
                logger.info("DOI %s in DB but no content, re-fetching...", doi)
                paper_id = self._fetch_and_store(conn, doi) or paper_id
        else:
            paper_id = self._fetch_and_store(conn, doi)

        if not paper_id:
            return {"status": "error", "message": f"Could not fetch DOI: {doi}"}

        result = {"doi": doi, "paper_id": paper_id, "steps": []}

        # Extract if not already done
        cur.execute("SELECT id FROM extraction_results WHERE paper_id = %s", (paper_id,))
        if not cur.fetchone():
            # Check if there is any content to extract
            cur.execute(
                "SELECT abstract, full_text, sections FROM raw_papers WHERE id = %s",
                (paper_id,),
            )
            content_row = cur.fetchone()
            has_content = bool(
                content_row and (
                    content_row["abstract"] or
                    content_row["full_text"] or
                    (content_row["sections"] and content_row["sections"] != {})
                )
            )
            if not has_content:
                return {
                    "doi": doi,
                    "paper_id": paper_id,
                    "status": "error",
                    "message": "No content found for this paper. "
                               "Tried CrossRef, Semantic Scholar, PubMed, and the publisher page. "
                               "The paper may be behind a paywall with no open-access version.",
                    "steps": [],
                }
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
        """Fetch paper metadata from CrossRef + Semantic Scholar fallback and store it."""
        import httpx
        import json
        import re
        from uuid import uuid4
        from datetime import date as _date

        title = "Unknown"
        authors: list[str] = []
        abstract = ""
        journal = None
        pub_date = None

        # ── Step 1: CrossRef ────────────────────────────────────────────────
        try:
            resp = httpx.get(
                f"https://api.crossref.org/works/{doi}",
                timeout=15,
                headers={"User-Agent": "Decoded/0.1 mailto:research@decoded.ai"},
            )
            if resp.status_code == 200:
                data = resp.json()["message"]
                title_parts = data.get("title", [])
                title = title_parts[0] if title_parts else "Unknown"
                for a in data.get("author", []):
                    name = f"{a.get('given', '')} {a.get('family', '')}".strip()
                    if name:
                        authors.append(name)
                if "abstract" in data:
                    abstract = re.sub(r"<[^>]+>", "", data["abstract"]).strip()
                journal_items = data.get("container-title", [])
                journal = journal_items[0] if journal_items else None
                if "published" in data:
                    parts = data["published"].get("date-parts", [[]])[0]
                    if parts:
                        pub_date = _date(parts[0], parts[1] if len(parts) > 1 else 1, parts[2] if len(parts) > 2 else 1)
                logger.info("CrossRef OK for %s: title=%s abstract=%s", doi, bool(title), bool(abstract))
        except Exception as exc:
            logger.warning("CrossRef fetch failed for %s: %s", doi, exc)

        # ── Step 2: Semantic Scholar fallback for abstract ──────────────────
        if not abstract:
            try:
                s2_url = f"https://api.semanticscholar.org/graph/v1/paper/DOI:{doi}"
                resp2 = httpx.get(
                    s2_url,
                    params={"fields": "abstract,title,authors,year,venue,externalIds"},
                    timeout=15,
                    headers={"User-Agent": "Decoded/0.1 mailto:research@decoded.ai"},
                )
                if resp2.status_code == 200:
                    s2 = resp2.json()
                    if s2.get("abstract"):
                        abstract = s2["abstract"].strip()
                        logger.info("Semantic Scholar provided abstract for %s", doi)
                    if title == "Unknown" and s2.get("title"):
                        title = s2["title"]
                    if not authors:
                        authors = [a.get("name", "") for a in s2.get("authors", [])[:10] if a.get("name")]
                    if not journal and s2.get("venue"):
                        journal = s2["venue"]
                    if not pub_date and s2.get("year"):
                        try:
                            pub_date = _date(int(s2["year"]), 1, 1)
                        except (ValueError, TypeError):
                            pass
                    # PMC ID for potential full-text retrieval
                    ext_ids = s2.get("externalIds", {})
                    pmc_id = ext_ids.get("PubMedCentral")
                    if pmc_id:
                        logger.info("Semantic Scholar found PMC ID %s for %s", pmc_id, doi)
            except Exception as exc:
                logger.warning("Semantic Scholar fetch failed for %s: %s", doi, exc)

        # ── Step 3: PubMed efetch fallback ──────────────────────────────────
        if not abstract:
            try:
                # Search PubMed by DOI
                search_resp = httpx.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi",
                    params={"db": "pubmed", "term": f"{doi}[doi]", "retmode": "json"},
                    timeout=15,
                )
                if search_resp.status_code == 200:
                    pmids = search_resp.json().get("esearchresult", {}).get("idlist", [])
                    if pmids:
                        fetch_resp = httpx.get(
                            "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                            params={"db": "pubmed", "id": pmids[0], "retmode": "xml", "rettype": "abstract"},
                            timeout=15,
                        )
                        if fetch_resp.status_code == 200:
                            from xml.etree import ElementTree as ET
                            root = ET.fromstring(fetch_resp.text)
                            ab_el = root.find(".//AbstractText")
                            if ab_el is not None and ab_el.text:
                                abstract = ab_el.text.strip()
                                logger.info("PubMed provided abstract for %s (PMID %s)", doi, pmids[0])
            except Exception as exc:
                logger.warning("PubMed fallback failed for %s: %s", doi, exc)

        # ── Step 4: Scrape publisher page via DOI redirect ──────────────────
        if not abstract:
            try:
                # Follow doi.org redirect to get publisher URL
                doi_resp = httpx.get(
                    f"https://doi.org/{doi}",
                    timeout=20,
                    follow_redirects=True,
                    headers={
                        "User-Agent": "Mozilla/5.0 (compatible; Decoded-Research/1.0; mailto:research@thedecodedhuman.com)",
                        "Accept": "text/html,application/xhtml+xml",
                    },
                )
                if doi_resp.status_code == 200:
                    html = doi_resp.text
                    publisher_url = str(doi_resp.url)
                    logger.info("DOI resolved to: %s", publisher_url)

                    # Try meta tags in priority order
                    meta_patterns = [
                        r'<meta\s+name=["\']citation_abstract["\']\s+content=["\'](.*?)["\']',
                        r'<meta\s+content=["\'](.*?)["\']\s+name=["\']citation_abstract["\']',
                        r'<meta\s+name=["\']dc\.description["\']\s+content=["\'](.*?)["\']',
                        r'<meta\s+name=["\']DC\.Description["\']\s+content=["\'](.*?)["\']',
                        r'<meta\s+property=["\']og:description["\']\s+content=["\'](.*?)["\']',
                        r'<meta\s+name=["\']description["\']\s+content=["\'](.*?)["\']',
                    ]
                    for pattern in meta_patterns:
                        m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
                        if m:
                            candidate = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                            # Reject generic site descriptions (too short or no scientific content)
                            if len(candidate) > 100:
                                abstract = candidate
                                logger.info("Scraped abstract from meta tag (%s) at %s", pattern[:30], publisher_url)
                                break

                    # Fallback: look for structured abstract in HTML body
                    if not abstract:
                        # Common abstract container patterns
                        body_patterns = [
                            r'<(?:div|section|p)[^>]*(?:class|id)=["\'][^"\']*abstract[^"\']*["\'][^>]*>(.*?)</(?:div|section|p)>',
                            r'<abstract[^>]*>(.*?)</abstract>',
                        ]
                        for pattern in body_patterns:
                            m = re.search(pattern, html, re.IGNORECASE | re.DOTALL)
                            if m:
                                candidate = re.sub(r"<[^>]+>", "", m.group(1)).strip()
                                if len(candidate) > 100:
                                    abstract = candidate[:5000]  # cap at 5k chars
                                    logger.info("Scraped abstract from HTML body at %s", publisher_url)
                                    break

                    # If we still don't have a title, try og:title
                    if title == "Unknown":
                        m = re.search(r'<meta\s+property=["\']og:title["\']\s+content=["\'](.*?)["\']', html, re.IGNORECASE)
                        if m:
                            title = m.group(1).strip()

            except Exception as exc:
                logger.warning("Publisher page scrape failed for %s: %s", doi, exc)

        if not abstract:
            logger.warning("No abstract found for DOI %s after CrossRef + S2 + PubMed + scrape", doi)

        # ── Upsert into raw_papers ──────────────────────────────────────────
        try:
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
                    abstract = COALESCE(EXCLUDED.abstract, raw_papers.abstract),
                    updated_at = NOW()
                RETURNING id
                """,
                (
                    paper_id,
                    doi,
                    title,
                    abstract or None,
                    json.dumps(authors),
                    journal,
                    doi,
                    pub_date,
                    json.dumps({"crossref": True, "has_abstract": bool(abstract)}),
                ),
            )
            result = cur.fetchone()
            conn.commit()
            logger.info("Stored DOI %s: '%s' (abstract: %s)", doi, title[:60], bool(abstract))
            return str(result[0]) if result else paper_id
        except Exception as exc:
            logger.warning("DB store failed for %s: %s", doi, exc)

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
