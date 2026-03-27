"""bioRxiv / medRxiv content API fetcher.

API docs: https://api.biorxiv.org/
Endpoints:
  /details/{server}/{interval}/{cursor}  — date-range search
  /details/{server}/{doi}/na/json        — single preprint by DOI
  /fulltext/pmc/{pmcid}                  — BioC fulltext (same as PMC BioC API)
"""

from __future__ import annotations

import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

BIORXIV_API = "https://api.biorxiv.org"
MEDRXIV_API = "https://api.medrxiv.org"


class BioRxivFetcher:
    """Fetch preprint metadata and (optionally) full text from bioRxiv/medRxiv.

    Uses the official content API which returns clean JSON.
    """

    def __init__(self, server: str = "biorxiv", timeout: float = 30.0):
        if server not in ("biorxiv", "medrxiv"):
            raise ValueError(f"server must be 'biorxiv' or 'medrxiv', got '{server}'")
        self.server = server
        self.base_url = BIORXIV_API if server == "biorxiv" else MEDRXIV_API
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def search_by_date(
        self,
        date_from: str,
        date_to: str,
        cursor: int = 0,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """Fetch preprints in a date range. Paginates automatically.

        date_from / date_to: 'YYYY-MM-DD'
        Returns list of preprint metadata dicts.
        """
        results: list[dict] = []
        while len(results) < max_results:
            batch = await self._fetch_page(date_from, date_to, cursor)
            if not batch:
                break
            results.extend(batch)
            cursor += len(batch)
            if len(batch) < 100:  # API returns ≤100 per page
                break

        return results[:max_results]

    async def get_by_doi(self, doi: str) -> dict[str, Any] | None:
        """Fetch a single preprint by DOI."""
        url = f"{self.base_url}/details/{self.server}/{doi}/na/json"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                collection = data.get("collection", [])
                if collection:
                    return self._normalize(collection[0])
        except Exception as exc:
            logger.warning("bioRxiv DOI fetch failed for %s: %s", doi, exc)
        return None

    async def search_by_query(
        self,
        query: str,
        max_results: int = 100,
    ) -> list[dict[str, Any]]:
        """Use the bioRxiv search API (category search).

        Note: the official API doesn't have keyword search.
        We use the category endpoint to get recent papers in a category,
        or fall back to fetching recent papers and filtering by abstract.
        For proper keyword search, use PubMed instead.
        """
        # bioRxiv doesn't have a keyword search API; return empty and
        # let the caller use PubMed for keyword queries.
        logger.info(
            "bioRxiv has no keyword search API — use PubMed for '%s'. "
            "Returning empty.",
            query,
        )
        return []

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _fetch_page(
        self, date_from: str, date_to: str, cursor: int
    ) -> list[dict[str, Any]]:
        """Fetch one page of results from the content API."""
        url = f"{self.base_url}/details/{self.server}/{date_from}/{date_to}/{cursor}/json"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                resp.raise_for_status()
                data = resp.json()
                collection = data.get("collection", [])
                return [self._normalize(item) for item in collection]
        except Exception as exc:
            logger.warning("bioRxiv page fetch failed (cursor=%d): %s", cursor, exc)
            return []

    def _normalize(self, item: dict) -> dict[str, Any]:
        """Normalize API response to our standard schema."""
        # Handle date
        pub_date = item.get("date") or item.get("date_timestamp")
        pub_year = None
        if pub_date and len(pub_date) >= 4:
            try:
                pub_year = int(pub_date[:4])
            except ValueError:
                pass

        doi = item.get("doi", "")
        authors_raw = item.get("authors", "")
        # Authors come as "Lastname, F.; Lastname2, F2;" format
        authors = [a.strip() for a in authors_raw.split(";") if a.strip()]

        return {
            "source": self.server,
            "external_id": doi or item.get("preprint_doi", ""),
            "title": item.get("title", ""),
            "abstract": item.get("abstract", "") or None,
            "authors": authors,
            "journal": item.get("server", self.server),
            "pub_date": pub_date,
            "pub_year": pub_year,
            "doi": doi or None,
            "pmc_id": None,
            "version": item.get("version"),
            "category": item.get("category"),
            "jatsxml": item.get("jatsxml"),  # URL to JATS XML if available
            "mesh_terms": [],
            "keywords": [],
            "raw_metadata": item,
        }
