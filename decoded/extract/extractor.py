"""LLM extraction engine for scientific papers.

Uses Claude Haiku for cost-effective bulk extraction.
Parses structured XML output into ExtractionResult objects.
"""

from __future__ import annotations

import logging
import re
from typing import Any
from xml.etree import ElementTree as ET

import anthropic

from decoded.cost_tracker import calculate_cost
from decoded.extract.prompts import SYSTEM_PROMPT, build_extraction_prompt
from decoded.models.paper import (
    ExtractedClaim,
    ExtractedEntity,
    ExtractedMechanism,
    ExtractedMethod,
    ExtractionResult,
    StudyDesign,
)

logger = logging.getLogger(__name__)

# Default model — haiku is fast and cheap for bulk extraction
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

# Valid study designs
_VALID_DESIGNS = {d.value for d in StudyDesign}


class PaperExtractor:
    """Extract structured data from a paper using Claude.

    Args:
        model_id: Claude model to use (default: haiku for cost efficiency)
        max_tokens: Max output tokens per extraction call
    """

    def __init__(
        self,
        model_id: str = DEFAULT_MODEL,
        max_tokens: int = 4096,
    ):
        self.model_id = model_id
        self.max_tokens = max_tokens
        self._client = anthropic.Anthropic()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def extract(
        self,
        paper_id: str,
        title: str,
        abstract: str | None = None,
        full_text: str | None = None,
        sections: dict | None = None,
    ) -> ExtractionResult:
        """Run extraction for a single paper. Returns ExtractionResult."""
        prompt = build_extraction_prompt(
            title=title,
            abstract=abstract,
            full_text=full_text,
            sections=sections,
        )

        response = self._client.messages.create(
            model=self.model_id,
            max_tokens=self.max_tokens,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw_text = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = calculate_cost(self.model_id, input_tokens, output_tokens)

        logger.debug(
            "Extracted paper %s: %d/%d tokens, $%.4f",
            paper_id, input_tokens, output_tokens, cost,
        )

        parsed = self._parse_xml_response(raw_text)
        # Retry once with higher token limit if XML was truncated/missing
        if not parsed and response.stop_reason == "max_tokens":
            logger.debug("Retrying %s with higher token limit", paper_id)
            retry_resp = self._client.messages.create(
                model=self.model_id,
                max_tokens=8192,
                system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = retry_resp.content[0].text
            input_tokens += retry_resp.usage.input_tokens
            output_tokens += retry_resp.usage.output_tokens
            cost += calculate_cost(self.model_id, retry_resp.usage.input_tokens, retry_resp.usage.output_tokens)
            parsed = self._parse_xml_response(raw_text)
        result = self._build_result(
            paper_id=paper_id,
            parsed=parsed,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost=cost,
        )
        return result

    # ------------------------------------------------------------------
    # XML parsing
    # ------------------------------------------------------------------

    def _parse_xml_response(self, text: str) -> dict[str, Any]:
        """Extract and parse the <extraction> XML block from LLM response."""
        # Find the XML block
        match = re.search(r"<extraction>.*?</extraction>", text, re.DOTALL)
        if not match:
            logger.warning("No <extraction> block found in response")
            return {}

        xml_str = match.group(0)
        # Remove XML comments (LLM sometimes leaves them)
        xml_str = re.sub(r"<!--.*?-->", "", xml_str, flags=re.DOTALL)

        try:
            root = ET.fromstring(xml_str)
        except ET.ParseError as exc:
            logger.warning("XML parse error: %s\nText: %s", exc, xml_str[:500])
            return {}

        result: dict[str, Any] = {}

        def text(tag: str) -> str | None:
            el = root.find(tag)
            return el.text.strip() if el is not None and el.text else None

        # Scalar fields
        result["study_design"] = text("study_design")
        result["sample_size_raw"] = text("sample_size")
        result["population"] = text("population")
        result["intervention"] = text("intervention")
        result["comparator"] = text("comparator")
        result["primary_outcome"] = text("primary_outcome")
        result["funding"] = text("funding")
        result["conflicts"] = text("conflicts")

        # Secondary outcomes (comma-separated string → list)
        sec_out = text("secondary_outcomes")
        if sec_out:
            result["secondary_outcomes"] = [s.strip() for s in sec_out.split(",") if s.strip()]
        else:
            result["secondary_outcomes"] = []

        # Key findings
        result["key_findings"] = [
            el.text.strip()
            for el in root.findall(".//key_findings/finding")
            if el.text and el.text.strip()
        ]

        # Entities (with LLM-provided confidence)
        result["entities"] = []
        for el in root.findall(".//entities/entity"):
            etype = el.get("type", "unknown")
            conf = el.get("confidence", "0.5")
            name = el.text.strip() if el.text else ""
            if name:
                result["entities"].append({"type": etype, "text": name, "confidence": conf})

        # Claims (with LLM-provided confidence)
        result["claims"] = []
        for el in root.findall(".//claims/claim"):
            claim_type = el.get("type", "descriptive")
            strength = el.get("strength", "moderate")
            conf = el.get("confidence", "0.5")
            text_val = el.text.strip() if el.text else ""
            if text_val:
                result["claims"].append({
                    "type": claim_type,
                    "strength": strength,
                    "text": text_val,
                    "confidence": conf,
                })

        # Mechanisms (with LLM-provided confidence)
        result["mechanisms"] = []
        for el in root.findall(".//mechanisms/mechanism"):
            desc_el = el.find("description")
            up_el = el.find("upstream")
            down_el = el.find("downstream")
            int_el = el.find("interaction")
            conf = el.get("confidence", "0.5")
            desc = desc_el.text.strip() if desc_el is not None and desc_el.text else ""
            if desc:
                result["mechanisms"].append({
                    "description": desc,
                    "upstream": up_el.text.strip() if up_el is not None and up_el.text else None,
                    "downstream": down_el.text.strip() if down_el is not None and down_el.text else None,
                    "interaction": int_el.text.strip() if int_el is not None and int_el.text else None,
                    "confidence": conf,
                })

        # Methods
        result["methods"] = []
        for el in root.findall(".//methods/method"):
            cat = el.get("category", "other")
            name = el.text.strip() if el.text else ""
            if name:
                result["methods"].append({"name": name, "category": cat})

        # Limitations
        result["limitations"] = [
            el.text.strip()
            for el in root.findall(".//limitations/limitation")
            if el.text and el.text.strip()
        ]

        return result

    def _build_result(
        self,
        paper_id: str,
        parsed: dict[str, Any],
        input_tokens: int,
        output_tokens: int,
        cost: float,
    ) -> ExtractionResult:
        """Convert parsed dict → ExtractionResult."""
        # Study design
        design_raw = (parsed.get("study_design") or "unknown").lower().strip()
        # Normalize some common variations
        design_map = {
            "randomized controlled trial": "rct",
            "randomized": "rct",
            "rct": "rct",
            "systematic review": "systematic_review",
            "meta-analysis": "meta_analysis",
            "meta_analysis": "meta_analysis",
            "case-control": "case_control",
            "case control": "case_control",
            "cross-sectional": "cross_sectional",
            "in vitro": "in_vitro",
        }
        design_raw = design_map.get(design_raw, design_raw)
        if design_raw not in _VALID_DESIGNS:
            design_raw = "unknown"
        study_design = StudyDesign(design_raw)

        # Sample size
        sample_size = None
        raw_ss = parsed.get("sample_size_raw")
        if raw_ss and raw_ss.lower() not in ("null", "none", "n/a", "unknown", ""):
            try:
                sample_size = int(re.sub(r"[^\d]", "", raw_ss) or 0) or None
            except (ValueError, TypeError):
                pass

        # Entities — use LLM-provided confidence, fallback to 0.5
        entities = [
            ExtractedEntity(
                text=e["text"],
                entity_type=e.get("type", "unknown"),
                confidence=min(1.0, max(0.0, float(e.get("confidence", 0.5)))),
            )
            for e in parsed.get("entities", [])
        ]

        # Claims — use LLM-provided confidence, fallback to 0.5
        claims = [
            ExtractedClaim(
                text=c["text"],
                claim_type=c.get("type", "descriptive"),
                evidence_strength=c.get("strength", "moderate"),
                confidence=min(1.0, max(0.0, float(c.get("confidence", 0.5)))),
            )
            for c in parsed.get("claims", [])
        ]

        # Mechanisms — use LLM-provided confidence, fallback to 0.5
        mechanisms = [
            ExtractedMechanism(
                description=m["description"],
                upstream_entity=m.get("upstream"),
                downstream_entity=m.get("downstream"),
                interaction_type=m.get("interaction"),
                confidence=min(1.0, max(0.0, float(m.get("confidence", 0.5)))),
            )
            for m in parsed.get("mechanisms", [])
        ]

        # Methods
        methods = [
            ExtractedMethod(
                name=m["name"],
                category=m.get("category"),
            )
            for m in parsed.get("methods", [])
        ]

        # Null-safe strings
        def clean(s: str | None) -> str | None:
            if s and s.lower() not in ("null", "none", "n/a", "unknown", ""):
                return s
            return None

        return ExtractionResult(
            paper_id=paper_id,  # type: ignore[arg-type]
            model_id=self.model_id,
            study_design=study_design,
            sample_size=sample_size,
            population=clean(parsed.get("population")),
            intervention=clean(parsed.get("intervention")),
            comparator=clean(parsed.get("comparator")),
            primary_outcome=clean(parsed.get("primary_outcome")),
            secondary_outcomes=parsed.get("secondary_outcomes", []),
            entities=entities,
            claims=claims,
            mechanisms=mechanisms,
            methods=methods,
            key_findings=parsed.get("key_findings", []),
            limitations=parsed.get("limitations", []),
            funding_sources=[parsed["funding"]] if clean(parsed.get("funding")) else [],
            conflicts_of_interest=clean(parsed.get("conflicts")),
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            cost_usd=cost,
        )
