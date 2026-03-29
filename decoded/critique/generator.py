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

SYSTEM_PROMPT = """You are an expert scientific analyst who synthesizes research papers within the context of a larger corpus of biomedical literature.

Your role is NOT to summarize papers — researchers can read abstracts themselves. Your role is to produce Intelligence Briefs that surface NEW INSIGHTS that only emerge from analyzing this paper alongside its connections to other papers in the corpus. Be direct, specific, and honest."""


def _assess_data_quality(paper: dict) -> tuple[str, list[str], list[str]]:
    """Assess what data we have and what's missing. Returns (level, available, missing)."""
    available = []
    missing = []

    data_source = paper.get("data_source", "unknown")
    if data_source.startswith("full_text"):
        available.append("Full paper text")
    elif data_source == "abstract_only":
        missing.append("Full paper text (abstract only)")
    else:
        missing.append("Full paper text (unknown source)")

    for field, label in [
        ("study_design", "Study design"),
        ("population", "Study population"),
        ("primary_outcome", "Primary outcome"),
    ]:
        val = paper.get(field, "")
        if val and val.lower() not in ("unknown", "", "null", "none"):
            available.append(label)
        else:
            missing.append(label)

    findings = paper.get("key_findings") or []
    if isinstance(findings, str):
        try:
            findings = json.loads(findings)
        except (json.JSONDecodeError, TypeError):
            findings = []
    if len(findings) >= 2:
        available.append(f"{len(findings)} key findings")
    else:
        missing.append("Key findings (fewer than 2 extracted)")

    entity_count = paper.get("entity_count", 0) or 0
    claim_count = paper.get("claim_count", 0) or 0
    if entity_count >= 3:
        available.append(f"{entity_count} entities")
    else:
        missing.append(f"Entities (only {entity_count} extracted)")
    if claim_count >= 2:
        available.append(f"{claim_count} claims")
    else:
        missing.append(f"Claims (only {claim_count} extracted)")

    completeness = paper.get("extraction_completeness", 0) or 0

    if data_source.startswith("full_text") and completeness >= 0.5 and len(missing) <= 2:
        level = "high"
    elif completeness >= 0.3 and entity_count >= 3:
        level = "medium"
    else:
        level = "low"

    return level, available, missing


def _build_critique_prompt(paper: dict, connections: list[dict]) -> str:
    """Build the critique prompt from paper data with explicit data quality context."""
    authors = paper.get("authors") or []
    if isinstance(authors, str):
        authors = json.loads(authors)
    author_str = ", ".join(authors[:5]) if authors else "Unknown"

    findings = paper.get("key_findings") or []
    if isinstance(findings, str):
        findings = json.loads(findings)
    findings_str = "\n".join(f"- {f}" for f in findings) if findings else "Not extracted"

    conn_str = ""
    if connections:
        conn_parts = []
        for c in connections[:10]:
            conn_parts.append(
                f"- {c['connection_type'].upper()} → {c['connected_paper_title'][:80]}: {c['description'][:150]}"
            )
        conn_str = "\n\nKnown connections to other papers:\n" + "\n".join(conn_parts)

    abstract = paper.get("abstract") or ""
    data_quality, available, missing_data = _assess_data_quality(paper)

    data_context = f"""
DATA COMPLETENESS: {data_quality.upper()}
Available for analysis: {', '.join(available) if available else 'Minimal data'}
Missing or incomplete: {', '.join(missing_data) if missing_data else 'None'}

IMPORTANT: Your assessment can only be as good as the data available. If critical information is missing:
- Do NOT score methodology or statistical rigor above 5.0 if you cannot see the methods/results sections
- Note in weaknesses when your assessment is limited by incomplete data
- Do NOT present limitations of the data extraction as flaws of the paper itself
- Distinguish between "paper has this weakness" and "I cannot assess this because data is missing"
"""

    n_connections = len(connections) if connections else 0

    return f"""Analyze this scientific paper IN THE CONTEXT of its connections to other papers in our corpus.
{data_context}
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
{abstract}

Key findings extracted by AI:
{findings_str}
{conn_str}

CRITICAL INSTRUCTIONS:
Do NOT just summarize the paper — the researcher can read the abstract themselves.
Instead, your brief must answer: "What do I learn from this paper that I couldn't learn by reading it alone?"

Your "summary" MUST focus on CORPUS-LEVEL INSIGHTS:
- How does this paper change the picture when combined with its {n_connections} connected papers?
- Does it confirm, contradict, or extend findings from connected papers?
- What questions does it open when read alongside the related work?
- What patterns emerge from the connections that aren't obvious from this paper alone?

If there are no connections, focus on: what gap does this paper fill in the corpus?
What existing papers in the corpus should be re-evaluated in light of this one?

Your "strengths" should highlight what this paper ADDS to the corpus (not just "large sample size").
Your "weaknesses" should highlight where this paper CONFLICTS with or FAILS TO ADDRESS gaps visible from the corpus.
Your "red_flags" should ONLY contain genuine methodological concerns — NOT extraction artifacts or missing metadata.

Produce your Intelligence Brief in this exact JSON format:
{{
  "overall_quality": "high|medium|low",
  "methodology_score": 0.0-10.0,
  "reproducibility_score": 0.0-10.0,
  "novelty_score": 0.0-10.0,
  "statistical_rigor": 0.0-10.0,
  "strengths": ["strength 1 — focus on corpus-level value", "strength 2"],
  "weaknesses": ["weakness 1 — focus on corpus-level gaps", "weakness 2"],
  "red_flags": ["ONLY genuine methodological red flags — empty list if none"],
  "summary": "2-3 sentences: what does this paper mean IN CONTEXT of the connected papers? What new insight emerges from the connections? Do NOT just summarize the paper.",
  "recommendation": "read|skim|skip|replicate|build_on"
}}

Scoring guide:
- methodology_score: rigor of study design, controls, sample size (cap at 5.0 if methods not visible)
- reproducibility_score: clarity of methods, data availability, code sharing
- novelty_score: how new are the findings RELATIVE TO THE CONNECTED PAPERS in this corpus
- statistical_rigor: appropriate tests, effect sizes, confidence intervals (cap at 5.0 if stats not visible)

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
    ) -> PaperCritique | None:
        """Generate a critique for a single paper. Returns None if data is insufficient."""
        data_quality, available, missing = _assess_data_quality(paper)

        entity_count = paper.get("entity_count", 0) or 0
        claim_count = paper.get("claim_count", 0) or 0
        if entity_count < 2 and claim_count < 1 and not paper.get("abstract"):
            logger.warning("Skipping critique for %s — insufficient data (entities=%d, claims=%d)",
                           paper.get("id"), entity_count, claim_count)
            return None

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
            brief_confidence=data_quality,
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
