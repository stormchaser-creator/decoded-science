"""Extract corresponding author contact information from paper metadata.

Sources:
1. raw_metadata field (PubMed XML often contains affiliation/email)
2. CrossRef API (corresponding author email sometimes available)
3. PubMed E-utilities (author affiliation)
4. DOI → publisher page (not scraped — out of scope)
"""

from __future__ import annotations

import logging
import re
import time
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Common academic email pattern
EMAIL_RE = re.compile(r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}")

# Throttle PubMed API calls
_PUBMED_DELAY = 0.34  # ~3 req/s (10/s with API key)


def extract_from_metadata(raw_metadata: dict) -> list[str]:
    """Extract emails from already-stored metadata."""
    emails = []
    if not raw_metadata:
        return emails

    # Search all string values recursively
    def _search(obj):
        if isinstance(obj, str):
            found = EMAIL_RE.findall(obj)
            emails.extend(found)
        elif isinstance(obj, dict):
            for v in obj.values():
                _search(v)
        elif isinstance(obj, list):
            for item in obj:
                _search(item)

    _search(raw_metadata)
    return list(set(emails))


def fetch_pubmed_author_email(pmid: str | None, doi: str | None = None) -> dict[str, Any]:
    """Query PubMed E-utilities for author affiliations and emails.

    Returns dict with 'corresponding_author', 'email', 'affiliation'.
    """
    result = {
        "corresponding_author": None,
        "email": None,
        "affiliation": None,
        "source": "pubmed",
    }

    if not pmid and not doi:
        return result

    # If we only have DOI, find the PMID first
    if not pmid and doi:
        pmid = _doi_to_pmid(doi)
        if not pmid:
            return result

    try:
        time.sleep(_PUBMED_DELAY)
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
        params = {
            "db": "pubmed",
            "id": pmid,
            "retmode": "xml",
            "rettype": "abstract",
        }
        resp = httpx.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return result

        xml_text = resp.text

        # Extract corresponding author info
        # PubMed XML: <AffiliationInfo><Affiliation>...</Affiliation></AffiliationInfo>
        affil_matches = re.findall(
            r"<Affiliation>(.*?)</Affiliation>", xml_text, re.DOTALL
        )
        for affil in affil_matches:
            affil = re.sub(r"<[^>]+>", "", affil).strip()
            emails = EMAIL_RE.findall(affil)
            if emails:
                result["email"] = emails[0]
                result["affiliation"] = affil[:300]
                break

        # Try to get last author (often corresponding)
        author_matches = re.findall(
            r"<Author[^>]*>.*?<LastName>(.*?)</LastName>.*?<ForeName>(.*?)</ForeName>",
            xml_text,
            re.DOTALL,
        )
        if author_matches:
            last = author_matches[-1]
            result["corresponding_author"] = f"{last[1]} {last[0]}".strip()

    except Exception as exc:
        logger.warning("PubMed fetch failed for PMID %s: %s", pmid, exc)

    return result


def _doi_to_pmid(doi: str) -> str | None:
    """Convert DOI to PubMed ID via E-utilities."""
    try:
        time.sleep(_PUBMED_DELAY)
        url = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
        params = {
            "db": "pubmed",
            "term": f"{doi}[doi]",
            "retmode": "json",
        }
        resp = httpx.get(url, params=params, timeout=10)
        if resp.status_code == 200:
            ids = resp.json().get("esearchresult", {}).get("idlist", [])
            return ids[0] if ids else None
    except Exception as exc:
        logger.warning("DOI→PMID lookup failed for %s: %s", doi, exc)
    return None


def enrich_paper_contacts(papers: list[dict]) -> list[dict]:
    """Enrich a list of papers with contact information.

    For each paper, tries metadata → PubMed in order.
    Returns papers with added 'contact' field.
    """
    enriched = []
    for paper in papers:
        contact = {
            "corresponding_author": None,
            "email": None,
            "affiliation": None,
        }

        # Try existing metadata first (fast, no API call)
        meta = paper.get("raw_metadata") or {}
        emails_from_meta = extract_from_metadata(meta)
        if emails_from_meta:
            contact["email"] = emails_from_meta[0]

        # Try PubMed if no email found and we have PMID or DOI
        if not contact["email"]:
            pmid = paper.get("pmc_id") or paper.get("external_id") if paper.get("source") == "pubmed" else None
            doi = paper.get("doi")
            if pmid or doi:
                pubmed_info = fetch_pubmed_author_email(pmid, doi)
                contact.update(pubmed_info)

        # Fall back to first/last author from authors list
        if not contact["corresponding_author"]:
            authors = paper.get("authors") or []
            if isinstance(authors, str):
                import json
                try:
                    authors = json.loads(authors)
                except Exception:
                    authors = [authors]
            if authors:
                contact["corresponding_author"] = authors[-1]  # Last author often corresponding

        paper_copy = dict(paper)
        paper_copy["contact"] = contact
        enriched.append(paper_copy)

    return enriched
