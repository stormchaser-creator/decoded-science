"""PMC discovery via PubMed E-utilities.

Flow: esearch (query → PMIDs) → elink (PMIDs → PMCIDs)

XML parsing delegates to pubmed_tools (shared-libs) to avoid duplication.
Async HTTP and rate limiting remain here — pubmed_tools is sync-only.
"""

from __future__ import annotations

import asyncio
import logging
import os
import time
from xml.etree import ElementTree as ET

import httpx

from pubmed_tools import parse_pubmed_xml, parse_elink_xml, Article

logger = logging.getLogger(__name__)

ESEARCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/esearch.fcgi"
ELINK_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/elink.fcgi"
EFETCH_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"

# NCBI rate limits: 10 req/s with key, 3 req/s without
_DEFAULT_CONCURRENCY = 8
_DEFAULT_CONCURRENCY_NO_KEY = 3


def _article_to_dict(a: Article) -> dict:
    """Convert a pubmed_tools Article to the dict format the worker expects."""
    return {
        "pmid": a.pmid,
        "title": a.title,
        "abstract": a.abstract or None,
        "authors": a.authors,
        "journal": a.journal or None,
        "pub_date": a.pub_date or None,
        "doi": a.doi or None,
        "pmc_id": a.pmc_id or None,
        "mesh_terms": a.mesh_terms,
        "keywords": a.keywords,
    }


class PMCDiscoverer:
    """Discover PubMed papers and resolve to PMC IDs.

    Uses esearch to find PMIDs matching a query, then elink to map
    PMIDs → PMCIDs (open-access full text available in PMC).
    """

    def __init__(self, api_key: str | None = None, concurrency: int | None = None):
        self.api_key = api_key or os.environ.get("NCBI_API_KEY")
        if concurrency is None:
            concurrency = _DEFAULT_CONCURRENCY if self.api_key else _DEFAULT_CONCURRENCY_NO_KEY
        self._sem = asyncio.Semaphore(concurrency)
        # Track last request time for polite rate limiting
        self._last_request: float = 0.0
        self._min_interval = 0.11 if self.api_key else 0.34  # seconds between calls

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search_pmids(
        self,
        query: str,
        max_results: int = 200,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[str]:
        """Run esearch and return a list of PMIDs."""
        params: dict = {
            "db": "pubmed",
            "term": query,
            "retmax": str(max_results),
            "retmode": "xml",
            "usehistory": "y",
        }
        if date_from:
            params["mindate"] = date_from.replace("-", "/")
        if date_to:
            params["maxdate"] = date_to.replace("-", "/")
        if date_from or date_to:
            params["datetype"] = "pdat"
        if self.api_key:
            params["api_key"] = self.api_key

        xml_text = await self._get(ESEARCH_URL, params)
        root = ET.fromstring(xml_text)

        count_el = root.find("Count")
        total = int(count_el.text) if count_el is not None else 0
        pmids = [el.text for el in root.findall(".//IdList/Id") if el.text]

        logger.info("esearch '%s': %d total hits, retrieved %d PMIDs", query, total, len(pmids))
        return pmids

    async def pmids_to_pmcids(self, pmids: list[str]) -> dict[str, str]:
        """Map PMIDs → PMCIDs via elink. Returns {pmid: pmcid}."""
        if not pmids:
            return {}

        results: dict[str, str] = {}
        chunk_size = 200
        chunks = [pmids[i : i + chunk_size] for i in range(0, len(pmids), chunk_size)]

        for chunk in chunks:
            mapping = await self._elink_chunk(chunk)
            results.update(mapping)

        logger.info("elink: %d / %d PMIDs have PMCIDs", len(results), len(pmids))
        return results

    async def fetch_pubmed_records(self, pmids: list[str]) -> list[dict]:
        """Fetch PubMed XML records for a list of PMIDs and parse metadata."""
        if not pmids:
            return []

        records = []
        chunk_size = 200
        for i in range(0, len(pmids), chunk_size):
            chunk = pmids[i : i + chunk_size]
            chunk_records = await self._efetch_pubmed_chunk(chunk)
            records.extend(chunk_records)

        return records

    async def discover(
        self,
        query: str,
        max_results: int = 200,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[dict]:
        """Full discovery: search → fetch PubMed metadata → resolve PMCIDs.

        Returns list of dicts with keys:
            pmid, title, abstract, authors, journal, pub_date, doi,
            pmc_id, mesh_terms, keywords
        """
        pmids = await self.search_pmids(query, max_results, date_from, date_to)
        if not pmids:
            return []

        # Fetch metadata and PMCIDs in parallel
        records_task = asyncio.create_task(self.fetch_pubmed_records(pmids))
        pmcid_task = asyncio.create_task(self.pmids_to_pmcids(pmids))

        records, pmcid_map = await asyncio.gather(records_task, pmcid_task)

        # Merge PMC IDs into records
        for rec in records:
            pmid = rec.get("pmid", "")
            rec["pmc_id"] = pmcid_map.get(pmid)

        return records

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get(self, url: str, params: dict) -> str:
        """Rate-limited GET with semaphore."""
        async with self._sem:
            now = time.monotonic()
            elapsed = now - self._last_request
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            async with httpx.AsyncClient(timeout=30) as client:
                resp = await client.get(url, params=params)
                resp.raise_for_status()
            self._last_request = time.monotonic()
            return resp.text

    async def _elink_chunk(self, pmids: list[str]) -> dict[str, str]:
        """Run elink for one chunk of PMIDs → PMCIDs."""
        params = {
            "dbfrom": "pubmed",
            "db": "pmc",
            "linkname": "pubmed_pmc",
            "id": ",".join(pmids),
            "retmode": "xml",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        xml_text = await self._get(ELINK_URL, params)
        return parse_elink_xml(xml_text)

    async def _efetch_pubmed_chunk(self, pmids: list[str]) -> list[dict]:
        """Fetch PubMed XML for a chunk and parse into dicts."""
        params = {
            "db": "pubmed",
            "id": ",".join(pmids),
            "retmode": "xml",
            "rettype": "abstract",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        xml_text = await self._get(EFETCH_URL, params)
        # Delegate XML parsing to shared pubmed_tools
        articles = parse_pubmed_xml(xml_text)
        return [_article_to_dict(a) for a in articles]


# ---------------------------------------------------------------------------
# Standalone XML helpers used by bulk_pmc.py
# ---------------------------------------------------------------------------

def _el_text(el: ET.Element | None) -> str | None:
    """Get all text from element including tails of children."""
    if el is None:
        return None
    return "".join(el.itertext()).strip() or None


def _month_to_num(month: str) -> str:
    months = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }
    if month.isdigit():
        return month.zfill(2)
    return months.get(month[:3].lower(), "01")


def _extract_pub_date(article: ET.Element) -> str | None:
    """Extract publication date as ISO string."""
    for path in [
        ".//PubDate",
        ".//ArticleDate",
        ".//DateCompleted",
        ".//DateRevised",
    ]:
        date_el = article.find(path)
        if date_el is not None:
            year = date_el.findtext("Year")
            month = date_el.findtext("Month") or "01"
            day = date_el.findtext("Day") or "01"
            if year:
                month = _month_to_num(month)
                return f"{year}-{month}-{day}"
    return None


def _parse_pubmed_xml(xml_text: str) -> list[dict]:
    """Parse PubMed efetch XML into list of metadata dicts."""
    root = ET.fromstring(xml_text)
    records = []

    for article in root.findall(".//PubmedArticle"):
        rec: dict = {}

        pmid_el = article.find(".//PMID")
        rec["pmid"] = pmid_el.text if pmid_el is not None else ""

        title_el = article.find(".//ArticleTitle")
        rec["title"] = _el_text(title_el) or ""

        abstract_texts = article.findall(".//AbstractText")
        if abstract_texts:
            parts = []
            for el in abstract_texts:
                label = el.get("Label", "")
                text = _el_text(el) or ""
                if label:
                    parts.append(f"{label}: {text}")
                else:
                    parts.append(text)
            rec["abstract"] = " ".join(parts)
        else:
            rec["abstract"] = None

        authors = []
        for author in article.findall(".//AuthorList/Author"):
            last = author.findtext("LastName", "")
            first = author.findtext("ForeName", "") or author.findtext("Initials", "")
            name = f"{last}, {first}".strip(", ")
            if name:
                authors.append(name)
        rec["authors"] = authors

        journal_el = article.find(".//Journal/Title")
        if journal_el is None:
            journal_el = article.find(".//MedlineJournalInfo/MedlineTA")
        rec["journal"] = journal_el.text if journal_el is not None else None

        rec["pub_date"] = _extract_pub_date(article)

        doi = None
        for id_el in article.findall(".//ArticleIdList/ArticleId"):
            if id_el.get("IdType") == "doi":
                doi = id_el.text
                break
        rec["doi"] = doi

        mesh = [
            el.findtext("DescriptorName", "")
            for el in article.findall(".//MeshHeadingList/MeshHeading")
        ]
        rec["mesh_terms"] = [m for m in mesh if m]

        keywords = [
            el.text for el in article.findall(".//KeywordList/Keyword") if el.text
        ]
        rec["keywords"] = keywords

        records.append(rec)

    return records
