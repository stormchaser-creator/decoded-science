"""EuropePMC discoverer for bioRxiv/medRxiv preprint keyword search.

EuropePMC indexes both bioRxiv and medRxiv preprints (SRC:PPR) and provides
keyword search that the bioRxiv/medRxiv native APIs lack.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

import httpx

logger = logging.getLogger(__name__)

EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
_STOP_WORDS = frozenset([
    "the", "and", "for", "with", "from", "human", "host", "cell",
    "gut", "disease", "health", "role", "study", "using", "into",
])


class EuropePMCDiscoverer:
    """Search bioRxiv/medRxiv preprints via EuropePMC REST API.

    EuropePMC is the official preprint indexer and supports full keyword
    search via SRC:PPR (preprint repositories).
    """

    def __init__(self, timeout: float = 30.0, request_delay: float = 1.0):
        self.timeout = timeout
        self.request_delay = request_delay

    async def discover(
        self,
        query: str,
        max_results: int = 100,
        server: str = "biorxiv",  # "biorxiv", "medrxiv", or "both"
    ) -> list[dict[str, Any]]:
        """Search preprints. Returns list of normalized metadata dicts.

        Each dict has keys: source, external_id, title, abstract, authors,
        journal, pub_date, pub_year, doi, pmc_id, keywords, mesh_terms,
        raw_metadata.
        """
        results: list[dict] = []
        cursor_mark = "*"
        page_size = 25

        # Build keyword query — use 2 most specific terms for balance of precision/recall
        # (EuropePMC treats multi-word as AND; too many terms → zero results)
        terms = [
            t for t in query.split()
            if len(t) > 3 and t.lower() not in _STOP_WORDS
        ]
        terms.sort(key=len, reverse=True)
        keyword_str = " ".join(terms[:2])

        while len(results) < max_results:
            fetch_n = min(page_size, max_results - len(results))
            params = {
                "query": f"{keyword_str} SRC:PPR",
                "resultType": "core",
                "pageSize": fetch_n,
                "format": "json",
                "cursorMark": cursor_mark,
            }

            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.get(f"{EUROPEPMC_BASE}/search", params=params)
                    resp.raise_for_status()
                data = resp.json()
            except Exception as exc:
                logger.warning("EuropePMC search failed for '%s': %s", query[:60], exc)
                break

            page_results = data.get("resultList", {}).get("result", [])
            if not page_results:
                break

            for r in page_results:
                abstract = (r.get("abstractText") or "").strip().replace("\n", " ")
                if len(abstract) < 50:
                    continue

                doi = (r.get("doi") or "").strip()
                source_id = doi or r.get("id", "")
                if not source_id:
                    continue

                # Determine biorxiv vs medrxiv
                publisher = (
                    (r.get("bookOrReportDetails") or {}).get("publisher", "") or
                    r.get("source", "")
                ).lower()
                source = "medrxiv" if "medrxiv" in publisher else "biorxiv"

                if server != "both" and source != server:
                    continue

                authors = [
                    a.get("fullName") or a.get("lastName", "")
                    for a in (r.get("authorList") or {}).get("author", [])[:10]
                    if a.get("fullName") or a.get("lastName")
                ]

                pub_date = r.get("firstPublicationDate") or r.get("pubYear")
                pub_year = None
                if pub_date and len(str(pub_date)) >= 4:
                    try:
                        pub_year = int(str(pub_date)[:4])
                    except ValueError:
                        pass

                results.append({
                    "source": source,
                    "external_id": doi or source_id,
                    "title": (r.get("title") or "").replace("\n", " ").strip(),
                    "abstract": abstract,
                    "authors": [a for a in authors if a],
                    "journal": "medRxiv" if source == "medrxiv" else "bioRxiv",
                    "pub_date": pub_date,
                    "pub_year": pub_year,
                    "doi": doi or None,
                    "pmc_id": None,
                    "keywords": [],
                    "mesh_terms": [],
                    "raw_metadata": {
                        "europepmc_id": r.get("id"),
                        "source": source,
                        "hit_count": data.get("hitCount"),
                    },
                })

            next_cursor = data.get("nextCursorMark")
            if not next_cursor or next_cursor == cursor_mark or len(page_results) < page_size:
                break
            cursor_mark = next_cursor

            await asyncio.sleep(self.request_delay)

        logger.info(
            "EuropePMC '%s' (server=%s): %d preprints found",
            query[:60], server, len(results),
        )
        return results[:max_results]
