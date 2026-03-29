"""Intelligence Brief generator using Claude Sonnet.

Produces structured critiques of scientific papers including:
- Methodology assessment
- Statistical rigor evaluation
- Key strength/weakness analysis
- Red flag detection
- Actionable recommendation
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

import anthropic

from decoded.cost_tracker import CostTracker, calculate_cost
from decoded.models.paper import PaperCritique

logger = logging.getLogger(__name__)

CRITIQUE_MODEL = "claude-sonnet-4-6"

SYSTEM_PROMPT = """You are an expert scientific reviewer with deep expertise in biomedical research methodology, statistics, and research integrity.

Your role is to produce rigorous, actionable Intelligence Briefs that help researchers quickly assess papers. Be direct, specific, and honest. Flag genuine red flags without hyperbole."""


def _build_critique_prompt(paper: dict, connections: list[dict]) -> str:
    """Build the critique prompt from paper data."""
    authors = paper.get("authors") or []
    if isinstance(authors, str):
        authors = json.loads(authors)
    author_str = ", ".join(authors[:5]) if authors else "Unknown"

    findings = paper.get("key_findings") or []
    if isinstance(findings, str):
        findings = json.loads(findings)
    findings_str = "\n".join(f"- {f}" for f in findings[:5]) if findings else "Not extracted"

    conn_str = ""
    if connections:
        conn_parts = []
        for c in connections[:5]:
            conn_parts.append(
                f"- {c['connection_type'].upper()} → {c['connected_paper_title'][:60]}: {c['description'][:100]}"
            )
        conn_str = "\n\nKnown connections to other papers:\n" + "\n".join(conn_parts)

    abstract = paper.get("abstract") or ""
    return f"""Analyze this scientific paper and produce an Intelligence Brief.

PAPER DETAILS:
Title: {paper.get('title', 'Unknown')}
Authors: {author_str}
Journal: {paper.get('journal', 'Unknown')}
Published: {paper.get('published_date', 'Unknown')}
DOI: {paper.get('doi', 'Not available')}
Study design: {paper.get('study_design', 'Unknown')}
Population: {paper.get('population', 'Unknown')}
Primary outcome: {paper.get('primary_outcome', 'Unknown')}

Abstract:
{abstract[:1000]}

Key findings extracted by AI:
{findings_str}
{conn_str}

Produce your Intelligence Brief in this exact JSON format:
{{
  "overall_quality": "high|medium|low",
  "methodology_score": 0.0-10.0,
  "reproducibility_score": 0.0-10.0,
  "novelty_score": 0.0-10.0,
  "statistical_rigor": 0.0-10.0,
  "strengths": ["strength 1", "strength 2", "strength 3"],
  "weaknesses": ["weakness 1", "weakness 2"],
  "red_flags": ["red flag if any — empty list if none"],
  "summary": "2-3 sentence executive summary of what this paper found and why it matters",
  "recommendation": "read|skim|skip|replicate|build_on"
}}

Scoring guide:
- methodology_score: rigor of study design, controls, sample size
- reproducibility_score: clarity of methods, data availability, code sharing
- novelty_score: how new are the findings relative to known literature
- statistical_rigor: appropriate tests, effect sizes, confidence intervals, p-hacking risk

Be direct. If the paper has serious flaws, say so. If it's genuinely excellent, say so.
Return only the JSON, no markdown."""


class CritiqueGenerator:
    """Generate Intelligence Briefs for scientific papers using Claude Sonnet."""

    def __init__(
        self,
        model_id: str = CRITIQUE_MODEL,
        cost_tracker: CostTracker | None = None,
    ):
        self.model_id = model_id
        self._client = anthropic.Anthropic()
        self._cost_tracker = cost_tracker or CostTracker()

    def generate(
        self,
        paper: dict[str, Any],
        connections: list[dict[str, Any]] | None = None,
    ) -> PaperCritique:
        """Generate a critique for a single paper."""
        prompt = _build_critique_prompt(paper, connections or [])

        response = self._client.messages.create(
            model=self.model_id,
            max_tokens=2048,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = calculate_cost(self.model_id, input_tokens, output_tokens)

        self._cost_tracker.record(
            model_id=self.model_id,
            task="critique",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            paper_id=str(paper.get("id", "")),
        )

        parsed = self._parse_response(raw)

        return PaperCritique(
            paper_id=paper["id"],
            model_id=self.model_id,
            overall_quality=parsed.get("overall_quality", "medium"),
            methodology_score=float(parsed.get("methodology_score", 5.0)),
            reproducibility_score=float(parsed.get("reproducibility_score", 5.0)),
            novelty_score=float(parsed.get("novelty_score", 5.0)),
            statistical_rigor=float(parsed.get("statistical_rigor", 5.0)),
            strengths=parsed.get("strengths", []),
            weaknesses=parsed.get("weaknesses", []),
            red_flags=parsed.get("red_flags", []),
            summary=parsed.get("summary", ""),
            recommendation=parsed.get("recommendation", "skim"),
            prompt_tokens=input_tokens,
            completion_tokens=output_tokens,
            cost_usd=cost,
        )

    def _parse_response(self, text: str) -> dict[str, Any]:
        """Parse JSON response from the LLM."""
        text = text.strip()
        # Strip markdown code fences if present
        lines = text.split("\n")
        text = "\n".join(
            line for line in lines if not line.strip().startswith("```")
        ).strip()

        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Find balanced JSON object using brace counting
            start = text.find("{")
            if start != -1:
                depth = 0
                for i, ch in enumerate(text[start:], start):
                    if ch == "{":
                        depth += 1
                    elif ch == "}":
                        depth -= 1
                        if depth == 0:
                            try:
                                return json.loads(text[start:i + 1])
                            except json.JSONDecodeError:
                                break
            logger.warning("Could not parse critique JSON response — using defaults")
            return {
                "overall_quality": "medium",
                "methodology_score": 5.0,
                "reproducibility_score": 5.0,
                "novelty_score": 5.0,
                "statistical_rigor": 5.0,
                "strengths": [],
                "weaknesses": ["Could not parse response"],
                "red_flags": [],
                "summary": text[:300],
                "recommendation": "skim",
            }
