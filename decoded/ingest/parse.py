"""JATS XML and BioC JSON parsers for PMC full-text articles.

Extracts: title, abstract, authors, journal, pub_date, sections
(intro/methods/results/discussion/conclusion), references with DOIs,
full text concatenation.
"""

from __future__ import annotations

import gzip
import json
import logging
import re
from typing import Any
from xml.etree import ElementTree as ET

logger = logging.getLogger(__name__)

# Section title patterns → normalized key
_SECTION_PATTERNS: list[tuple[str, str]] = [
    (r"intro", "introduction"),
    (r"background", "introduction"),
    (r"method|material|protocol|procedure", "methods"),
    (r"result", "results"),
    (r"finding", "results"),
    (r"discussion|interpret", "discussion"),
    (r"conclusion|summary|closing", "conclusion"),
    (r"abstract", "abstract"),
    (r"supplement", "supplementary"),
    (r"acknowledge", "acknowledgements"),
    (r"reference|bibliograph", "references_section"),
    (r"funding|financ", "funding"),
    (r"conflict|compet", "conflict_of_interest"),
]


def _classify_section(title: str) -> str:
    """Map a section title to a normalized key."""
    lower = title.lower()
    for pattern, key in _SECTION_PATTERNS:
        if re.search(pattern, lower):
            return key
    return "other"


# ---------------------------------------------------------------------------
# JATS XML Parser
# ---------------------------------------------------------------------------


class JATSParser:
    """Parse JATS XML (from PMC efetch) into structured metadata."""

    def parse(self, xml_bytes: bytes) -> dict[str, Any]:
        """Parse JATS XML bytes → structured dict."""
        if xml_bytes[:2] == b"\x1f\x8b":
            xml_bytes = gzip.decompress(xml_bytes)

        try:
            root = ET.fromstring(xml_bytes)
        except ET.ParseError as exc:
            logger.error("JATS XML parse error: %s", exc)
            return {}

        result: dict[str, Any] = {}

        # Title
        result["title"] = self._extract_title(root)

        # Abstract
        result["abstract"] = self._extract_abstract(root)

        # Authors
        result["authors"] = self._extract_authors(root)

        # Journal
        result["journal"] = self._extract_journal(root)

        # Publication date
        result["pub_date"], result["pub_year"] = self._extract_pub_date(root)

        # DOI
        result["doi"] = self._extract_doi(root)

        # Sections
        result["sections"] = self._extract_sections(root)

        # References
        result["references"] = self._extract_references(root)
        result["reference_count"] = len(result["references"])

        # Full text (concatenation of all body sections)
        result["full_text"] = self._extract_full_text(root, result["sections"])

        return result

    # ------------------------------------------------------------------
    # Field extractors
    # ------------------------------------------------------------------

    def _extract_title(self, root: ET.Element) -> str:
        el = root.find(".//article-title")
        if el is not None:
            return "".join(el.itertext()).strip()
        return ""

    def _extract_abstract(self, root: ET.Element) -> str | None:
        abstract_el = root.find(".//abstract")
        if abstract_el is None:
            return None
        parts = []
        for p in abstract_el.findall(".//p"):
            text = "".join(p.itertext()).strip()
            if text:
                parts.append(text)
        if not parts:
            text = "".join(abstract_el.itertext()).strip()
            return text or None
        return " ".join(parts)

    def _extract_authors(self, root: ET.Element) -> list[str]:
        authors = []
        for contrib in root.findall(".//contrib[@contrib-type='author']"):
            surname = contrib.findtext(".//surname", "")
            given = contrib.findtext(".//given-names", "")
            name = f"{surname}, {given}".strip(", ")
            if name:
                authors.append(name)
        return authors

    def _extract_journal(self, root: ET.Element) -> str | None:
        for path in [
            ".//journal-title",
            ".//journal-id[@journal-id-type='nlm-ta']",
            ".//journal-id[@journal-id-type='iso-abbrev']",
        ]:
            el = root.find(path)
            if el is not None and el.text:
                return el.text.strip()
        return None

    def _extract_pub_date(self, root: ET.Element) -> tuple[str | None, int | None]:
        for pub_type in ["epub", "ppub", "pmc-release", None]:
            if pub_type:
                el = root.find(f".//pub-date[@pub-type='{pub_type}']")
            else:
                el = root.find(".//pub-date")
            if el is not None:
                year = el.findtext("year")
                month = el.findtext("month") or "01"
                day = el.findtext("day") or "01"
                if year:
                    pub_date = f"{year}-{month.zfill(2)}-{day.zfill(2)}"
                    return pub_date, int(year)
        return None, None

    def _extract_doi(self, root: ET.Element) -> str | None:
        for id_el in root.findall(".//article-id"):
            if id_el.get("pub-id-type") == "doi" and id_el.text:
                return id_el.text.strip()
        return None

    def _extract_sections(self, root: ET.Element) -> dict[str, str]:
        """Extract named sections from article body."""
        sections: dict[str, str] = {}
        body = root.find(".//body")
        if body is None:
            return sections

        for sec in body.findall(".//sec"):
            # Get section title
            title_el = sec.find("title")
            if title_el is None:
                continue
            title = "".join(title_el.itertext()).strip()
            if not title:
                continue

            key = _classify_section(title)

            # Extract text (paragraphs only, not nested sections)
            paragraphs = []
            for child in sec:
                if child.tag == "p":
                    text = "".join(child.itertext()).strip()
                    if text:
                        paragraphs.append(text)

            text = " ".join(paragraphs).strip()
            if text:
                # Append if key already exists (multiple subsections)
                if key in sections:
                    sections[key] = sections[key] + " " + text
                else:
                    sections[key] = text

        return sections

    def _extract_references(self, root: ET.Element) -> list[dict[str, str | None]]:
        """Extract reference list with titles, authors, DOIs."""
        refs = []
        for ref in root.findall(".//ref-list/ref"):
            entry: dict[str, str | None] = {"ref_id": ref.get("id")}

            # Title
            article_title = ref.find(".//article-title")
            source = ref.find(".//source")
            if article_title is not None:
                entry["title"] = "".join(article_title.itertext()).strip()
            elif source is not None:
                entry["title"] = "".join(source.itertext()).strip()
            else:
                entry["title"] = None

            # Authors
            author_names = []
            for name_el in ref.findall(".//person-group[@person-group-type='author']/name"):
                surname = name_el.findtext("surname", "")
                given = name_el.findtext("given-names", "")
                author_names.append(f"{surname} {given}".strip())
            entry["authors"] = "; ".join(author_names) if author_names else None

            # Year
            year_el = ref.find(".//year")
            entry["year"] = year_el.text if year_el is not None else None

            # DOI
            doi = None
            for pub_id in ref.findall(".//pub-id"):
                if pub_id.get("pub-id-type") == "doi" and pub_id.text:
                    doi = pub_id.text.strip()
                    break
            entry["doi"] = doi

            # PMID
            pmid = None
            for pub_id in ref.findall(".//pub-id"):
                if pub_id.get("pub-id-type") == "pmid" and pub_id.text:
                    pmid = pub_id.text.strip()
                    break
            entry["pmid"] = pmid

            refs.append(entry)
        return refs

    def _extract_full_text(self, root: ET.Element, sections: dict[str, str]) -> str | None:
        """Build full text from sections dict, or fall back to body text."""
        if sections:
            parts = []
            for key in ["introduction", "methods", "results", "discussion", "conclusion"]:
                if key in sections:
                    parts.append(sections[key])
            if parts:
                return " ".join(parts)

        # Fallback: all body text
        body = root.find(".//body")
        if body is not None:
            text = "".join(body.itertext()).strip()
            return text or None
        return None


# ---------------------------------------------------------------------------
# BioC JSON Parser
# ---------------------------------------------------------------------------


class BioCParser:
    """Parse BioC JSON (from NCBI BioC API) into structured metadata.

    The BioC format has a list of 'passages', each with a type and text.
    """

    def parse(self, bioc_bytes: bytes) -> dict[str, Any]:
        """Parse BioC JSON bytes → structured dict."""
        if bioc_bytes[:2] == b"\x1f\x8b":
            bioc_bytes = gzip.decompress(bioc_bytes)

        try:
            data = json.loads(bioc_bytes)
        except json.JSONDecodeError as exc:
            logger.error("BioC JSON parse error: %s", exc)
            return {}

        # Handle both wrapped {documents: [...]} and bare document formats
        documents = data.get("documents") or data.get("PubTator3") or []
        if not documents and isinstance(data, dict) and "passages" in data:
            documents = [data]

        if not documents:
            return {}

        doc = documents[0]
        passages = doc.get("passages", [])

        result: dict[str, Any] = {}
        result["title"] = self._get_passage_text(passages, "title")
        result["abstract"] = self._get_passage_text(passages, "abstract")

        # Sections
        sections: dict[str, str] = {}
        full_text_parts: list[str] = []

        for passage in passages:
            infons = passage.get("infons", {})
            ptype = (infons.get("type") or infons.get("section_type") or "").lower()
            text = passage.get("text", "").strip()
            if not text:
                continue

            full_text_parts.append(text)

            # Map type to section key
            key = _classify_section(ptype) if ptype else None
            if key and key not in ("abstract",):
                if key in sections:
                    sections[key] = sections[key] + " " + text
                else:
                    sections[key] = text

        result["sections"] = sections
        result["full_text"] = " ".join(full_text_parts) or None

        # Metadata from doc-level infons
        infons = doc.get("infons", {})
        result["doi"] = infons.get("doi")
        result["journal"] = infons.get("journal")
        result["pub_date"] = infons.get("year")
        result["pub_year"] = int(infons["year"]) if infons.get("year", "").isdigit() else None

        # Authors not typically in BioC — caller merges from PubMed metadata
        result["authors"] = []
        result["references"] = []
        result["reference_count"] = 0

        return result

    def _get_passage_text(self, passages: list[dict], passage_type: str) -> str | None:
        for p in passages:
            infons = p.get("infons", {})
            ptype = (infons.get("type") or infons.get("section_type") or "").lower()
            if passage_type in ptype:
                return p.get("text", "").strip() or None
        return None


# ---------------------------------------------------------------------------
# Unified parser entry point
# ---------------------------------------------------------------------------


def parse_article(fmt: str, content: bytes) -> dict[str, Any]:
    """Dispatch to the right parser based on format string."""
    if fmt == "bioc":
        return BioCParser().parse(content)
    elif fmt == "jats":
        return JATSParser().parse(content)
    else:
        logger.warning("Unknown format '%s', trying JATS", fmt)
        return JATSParser().parse(content)
