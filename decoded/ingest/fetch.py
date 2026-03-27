"""PMC full-text fetcher.

Primary: BioC API (JSON) — structured, clean
Fallback: efetch JATS XML via E-utilities
Storage: compressed XML on local disk at data/raw_xml/
"""

from __future__ import annotations

import gzip
import json
import logging
import os
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# BioC JSON API for PMC open-access full text
BIOC_API_URL = "https://www.ncbi.nlm.nih.gov/research/biorxiv/api/fulltext/pmc/{pmcid}"

# E-utilities efetch for JATS XML (works for OA articles)
EFETCH_XML_URL = (
    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi"
    "?db=pmc&id={pmcid}&rettype=full&retmode=xml"
)

# PMC OA API to get download links
PMC_OA_URL = "https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}&format=xml"

_DEFAULT_RAW_XML_DIR = Path(os.environ.get("RAW_XML_DIR", "data/raw_xml"))


class PMCFetcher:
    """Fetch full-text XML/JSON from PMC and store compressed on disk.

    For each PMC article we try:
      1. BioC JSON API (structured, preferred for parser)
      2. efetch JATS XML (always returns XML for OA articles)
      3. PMC OA API → direct XML download link

    The raw content is stored as gzip-compressed bytes at:
      {raw_xml_dir}/{pmcid}.xml.gz  (JATS XML)
      {raw_xml_dir}/{pmcid}.bioc.json.gz  (BioC JSON)
    """

    def __init__(
        self,
        raw_xml_dir: Path | str | None = None,
        api_key: str | None = None,
        timeout: float = 60.0,
    ):
        self.raw_xml_dir = Path(raw_xml_dir or _DEFAULT_RAW_XML_DIR)
        self.raw_xml_dir.mkdir(parents=True, exist_ok=True)
        self.api_key = api_key or os.environ.get("NCBI_API_KEY")
        self.timeout = timeout

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def xml_path(self, pmcid: str) -> Path:
        return self.raw_xml_dir / f"{pmcid}.xml.gz"

    def bioc_path(self, pmcid: str) -> Path:
        return self.raw_xml_dir / f"{pmcid}.bioc.json.gz"

    def is_cached(self, pmcid: str) -> bool:
        return self.xml_path(pmcid).exists() or self.bioc_path(pmcid).exists()

    async def fetch(self, pmcid: str) -> tuple[str, bytes] | None:
        """Fetch and store article. Returns (format, compressed_bytes) or None.

        format is 'bioc' or 'jats'.
        """
        if self.is_cached(pmcid):
            return self._load_cached(pmcid)

        # Try BioC JSON first
        result = await self._try_bioc(pmcid)
        if result:
            fmt, data = result
            gz = gzip.compress(data)
            self.bioc_path(pmcid).write_bytes(gz)
            logger.debug("Fetched %s via BioC (%d bytes compressed)", pmcid, len(gz))
            return "bioc", gz

        # Fallback: efetch JATS XML
        result = await self._try_efetch_xml(pmcid)
        if result:
            fmt, data = result
            gz = gzip.compress(data)
            self.xml_path(pmcid).write_bytes(gz)
            logger.debug("Fetched %s via efetch XML (%d bytes compressed)", pmcid, len(gz))
            return "jats", gz

        # Final fallback: OA API download link
        result = await self._try_oa_download(pmcid)
        if result:
            fmt, data = result
            gz = gzip.compress(data)
            self.xml_path(pmcid).write_bytes(gz)
            logger.debug("Fetched %s via OA download (%d bytes compressed)", pmcid, len(gz))
            return "jats", gz

        logger.warning("Could not fetch full text for %s", pmcid)
        return None

    def load_content(self, pmcid: str) -> tuple[str, bytes] | None:
        """Load cached content from disk. Returns (format, raw_bytes) or None."""
        cached = self._load_cached(pmcid)
        if cached is None:
            return None
        fmt, gz = cached
        return fmt, gzip.decompress(gz)

    # ------------------------------------------------------------------
    # Private fetch methods
    # ------------------------------------------------------------------

    async def _try_bioc(self, pmcid: str) -> tuple[str, bytes] | None:
        """Try BioC JSON API."""
        # Strip 'PMC' prefix for the API
        pmcid_num = pmcid.lstrip("PMC")
        url = f"https://www.ncbi.nlm.nih.gov/research/biorxiv/api/fulltext/pmc/PMC{pmcid_num}"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    # Validate it's JSON with content
                    data = resp.json()
                    if data.get("passages") or (
                        isinstance(data, dict) and "documents" in data
                    ):
                        return "bioc", resp.content
                    # Some returns are wrapped
                    return "bioc", resp.content
        except Exception as exc:
            logger.debug("BioC fetch failed for %s: %s", pmcid, exc)
        return None

    async def _try_efetch_xml(self, pmcid: str) -> tuple[str, bytes] | None:
        """Try efetch JATS XML from E-utilities."""
        pmcid_num = pmcid.lstrip("PMC")
        params = {
            "db": "pmc",
            "id": pmcid_num,
            "rettype": "full",
            "retmode": "xml",
        }
        if self.api_key:
            params["api_key"] = self.api_key

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(
                    "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/efetch.fcgi",
                    params=params,
                )
                if resp.status_code == 200 and b"<article" in resp.content:
                    return "jats", resp.content
        except Exception as exc:
            logger.debug("efetch XML failed for %s: %s", pmcid, exc)
        return None

    async def _try_oa_download(self, pmcid: str) -> tuple[str, bytes] | None:
        """Use PMC OA API to get download URL then fetch XML."""
        from xml.etree import ElementTree as ET

        url = f"https://www.ncbi.nlm.nih.gov/pmc/utils/oa/oa.fcgi?id={pmcid}&format=xml"
        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.get(url)
                if resp.status_code != 200:
                    return None

                root = ET.fromstring(resp.text)
                # Look for https link
                link_el = root.find(".//link[@format='xml']")
                if link_el is None:
                    return None
                href = link_el.get("href", "")
                if not href:
                    return None

                # href may be ftp:// or https://
                if href.startswith("ftp://"):
                    href = href.replace("ftp://", "https://", 1)

                xml_resp = await client.get(href, follow_redirects=True)
                if xml_resp.status_code == 200:
                    content = xml_resp.content
                    # May be gzip already
                    if content[:2] == b"\x1f\x8b":
                        content = gzip.decompress(content)
                    if b"<article" in content:
                        return "jats", content
        except Exception as exc:
            logger.debug("OA download failed for %s: %s", pmcid, exc)
        return None

    # ------------------------------------------------------------------
    # Cache helpers
    # ------------------------------------------------------------------

    def _load_cached(self, pmcid: str) -> tuple[str, bytes] | None:
        bioc = self.bioc_path(pmcid)
        if bioc.exists():
            return "bioc", bioc.read_bytes()
        xml = self.xml_path(pmcid)
        if xml.exists():
            return "jats", xml.read_bytes()
        return None
