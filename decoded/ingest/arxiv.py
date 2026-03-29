"""arXiv API discoverer for the Decoded ingest pipeline.

Uses the arXiv Atom API (export.arxiv.org) for keyword search.
arXiv asks for a 3-second delay between requests.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any
from xml.etree import ElementTree as ET

import httpx

logger = logging.getLogger(__name__)

ARXIV_API = "https://export.arxiv.org/api/query"
_ATOM_NS = "http://www.w3.org/2005/Atom"
_ARXIV_NS = "http://arxiv.org/schemas/atom"


class ArxivDiscoverer:
    """Search arXiv preprints via the arXiv Atom API."""

    def __init__(
        self,
        timeout: float = 60.0,
        request_delay: float = 3.0,  # arXiv ToS asks for 3s between calls
        categories: list[str] | None = None,
    ):
        self.timeout = timeout
        self.request_delay = request_delay
        # Default: quantitative biology broad categories (most relevant for Decoded)
        self.categories = categories or [
            "q-bio", "q-bio.GN", "q-bio.MN", "q-bio.PE",
            "q-bio.TO", "q-bio.NC", "q-bio.CB",
        ]

    async def discover(
        self,
        query: str,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """Search arXiv. Returns list of normalized metadata dicts."""
        results: list[dict] = []
        batch_size = 50
        start = 0

        # Build search query with category filter
        cat_filter = " OR ".join(f"cat:{c}" for c in self.categories)
        search_query = f"all:{query} AND ({cat_filter})"

        while len(results) < max_results:
            fetch_n = min(batch_size, max_results - len(results))
            params = {
                "search_query": search_query,
                "start": start,
                "max_results": fetch_n,
                "sortBy": "relevance",
                "sortOrder": "descending",
            }

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(ARXIV_API, params=params)
                    resp.raise_for_status()
                root = ET.fromstring(resp.text)
            except Exception as exc:
                logger.warning("arXiv search failed for '%s': %s", query[:60], exc)
                break

            entries = root.findall(f"{{{_ATOM_NS}}}entry")
            if not entries:
                break

            for entry in entries:
                title_el = entry.find(f"{{{_ATOM_NS}}}title")
                abstract_el = entry.find(f"{{{_ATOM_NS}}}summary")
                id_el = entry.find(f"{{{_ATOM_NS}}}id")
                published_el = entry.find(f"{{{_ATOM_NS}}}published")

                title = (title_el.text or "").strip().replace("\n", " ") if title_el is not None else ""
                abstract = (abstract_el.text or "").strip().replace("\n", " ") if abstract_el is not None else ""
                arxiv_url = (id_el.text or "").strip() if id_el is not None else ""

                if not abstract or len(abstract) < 50 or not arxiv_url:
                    continue

                # Extract arXiv ID: "http://arxiv.org/abs/1234.5678v2" → "1234.5678v2"
                arxiv_id = arxiv_url.split("/abs/")[-1].strip() if "/abs/" in arxiv_url else ""
                if not arxiv_id:
                    continue

                # DOI if available
                doi_el = entry.find(f"{{{_ARXIV_NS}}}doi")
                doi = doi_el.text.strip() if doi_el is not None and doi_el.text else None

                # Authors
                authors = []
                for author in entry.findall(f"{{{_ATOM_NS}}}author")[:10]:
                    name_el = author.find(f"{{{_ATOM_NS}}}name")
                    if name_el is not None and name_el.text:
                        authors.append(name_el.text.strip())

                pub_date = (published_el.text or "")[:10] if published_el is not None else None
                pub_year = None
                if pub_date and len(pub_date) >= 4:
                    try:
                        pub_year = int(pub_date[:4])
                    except ValueError:
                        pass

                # Categories for this entry
                entry_cats = [
                    t.get("term", "")
                    for t in entry.findall(f"{{{_ATOM_NS}}}category")
                ]

                results.append({
                    "source": "arxiv",
                    "external_id": arxiv_id,
                    "title": title,
                    "abstract": abstract,
                    "authors": authors,
                    "journal": "arXiv",
                    "pub_date": pub_date,
                    "pub_year": pub_year,
                    "doi": doi,
                    "pmc_id": None,
                    "keywords": entry_cats,
                    "mesh_terms": [],
                    "raw_metadata": {
                        "arxiv_id": arxiv_id,
                        "arxiv_url": arxiv_url,
                        "categories": entry_cats,
                    },
                })

            if len(entries) < fetch_n:
                break

            start += len(entries)
            await asyncio.sleep(self.request_delay)

        logger.info("arXiv '%s': %d papers found", query[:60], len(results))
        return results[:max_results]
