"""Phase 3: LLM-based connection validation and bridge hypothesis generation.

Uses Claude Sonnet to validate top candidates from graph + embedding phases,
and to generate bridge hypotheses for on-demand concept-to-concept queries.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from decoded.cost_tracker import CostTracker, calculate_cost

logger = logging.getLogger(__name__)

# Sonnet for connection quality — smart enough to see subtle links
VALIDATION_MODEL = "claude-sonnet-4-6"


class LLMDiscovery:
    """Validate candidate pairs and generate bridge hypotheses with Claude."""

    def __init__(
        self,
        model_id: str = VALIDATION_MODEL,
        cost_tracker: CostTracker | None = None,
    ):
        self.model_id = model_id
        self._client = anthropic.Anthropic()
        self._cost_tracker = cost_tracker or CostTracker()

    # ------------------------------------------------------------------
    # Candidate validation
    # ------------------------------------------------------------------

    def validate_pair(
        self,
        paper_a: dict,
        paper_b: dict,
        shared_entities: list[str] | None = None,
        discovery_method: str = "unknown",
    ) -> dict[str, Any] | None:
        """Validate a candidate paper pair and classify the connection.

        Returns a connection dict or None if no meaningful connection found.
        """
        prompt = self._build_validation_prompt(paper_a, paper_b, shared_entities, discovery_method)

        response = self._client.messages.create(
            model=self.model_id,
            max_tokens=1024,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        input_tokens = response.usage.input_tokens
        output_tokens = response.usage.output_tokens
        cost = calculate_cost(self.model_id, input_tokens, output_tokens)

        self._cost_tracker.record(
            model_id=self.model_id,
            task="connect",
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

        result = self._parse_validation(raw)
        if result:
            result["model_id"] = self.model_id
            result["prompt_tokens"] = input_tokens
            result["completion_tokens"] = output_tokens
            result["cost_usd"] = cost
            result["paper_a_id"] = paper_a["id"]
            result["paper_b_id"] = paper_b["id"]
        return result

    def _build_validation_prompt(
        self,
        paper_a: dict,
        paper_b: dict,
        shared_entities: list[str] | None,
        discovery_method: str,
    ) -> str:
        def paper_summary(p: dict) -> str:
            lines = [f"Title: {p.get('title', 'Unknown')}"]
            if p.get("abstract"):
                lines.append(f"Abstract: {p['abstract'][:400]}")
            findings = p.get("key_findings") or []
            if isinstance(findings, str):
                findings = json.loads(findings)
            if findings:
                lines.append("Key findings: " + "; ".join(findings[:3]))
            return "\n".join(lines)

        shared_str = ""
        if shared_entities:
            shared_str = f"\nShared elements: {', '.join(shared_entities[:10])}"

        return f"""You are a biomedical research analyst identifying meaningful connections between scientific papers.

PAPER A:
{paper_summary(paper_a)}

PAPER B:
{paper_summary(paper_b)}
{shared_str}
Discovery method: {discovery_method}

Analyze whether these papers have a scientifically meaningful connection. If yes, classify it and explain.

Respond in this exact JSON format (no markdown, no extra text):
{{
  "connected": true/false,
  "connection_type": "replicates|contradicts|extends|mechanism_for|shares_target|methodological_parallel|convergent_evidence|null",
  "description": "One clear sentence describing the connection",
  "confidence": 0.0-1.0,
  "novelty_score": 0.0-1.0,
  "supporting_evidence": ["evidence point 1", "evidence point 2"]
}}

If the connection is not meaningful or too superficial, set "connected": false."""

    def _parse_validation(self, text: str) -> dict | None:
        """Parse JSON response from LLM."""
        # Find JSON block
        text = text.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1])

        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            # Try to extract JSON
            import re
            match = re.search(r'\{.*\}', text, re.DOTALL)
            if not match:
                logger.warning("Could not parse LLM validation response")
                return None
            try:
                data = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

        if not data.get("connected"):
            return None

        return {
            "connection_type": data.get("connection_type", "unknown"),
            "description": data.get("description", ""),
            "confidence": float(data.get("confidence", 0.5)),
            "novelty_score": float(data.get("novelty_score", 0.5)),
            "supporting_evidence": data.get("supporting_evidence", []),
        }

    # ------------------------------------------------------------------
    # Bridge hypothesis generation
    # ------------------------------------------------------------------

    def generate_bridge_hypothesis(
        self,
        concept_a: str,
        concept_b: str,
        papers_a: list[dict],
        papers_b: list[dict],
        graph_paths: list[dict] | None = None,
        similar_papers: list[dict] | None = None,
    ) -> dict[str, Any]:
        """Generate a bridge hypothesis connecting two concepts.

        Used for the on-demand BRIDGE QUERY feature.
        """
        prompt = self._build_bridge_prompt(
            concept_a, concept_b, papers_a, papers_b, graph_paths, similar_papers
        )

        response = self._client.messages.create(
            model=self.model_id,
            max_tokens=2048,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        cost = calculate_cost(
            self.model_id,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )
        self._cost_tracker.record(
            model_id=self.model_id,
            task="bridge",
            input_tokens=response.usage.input_tokens,
            output_tokens=response.usage.output_tokens,
        )

        return {
            "concept_a": concept_a,
            "concept_b": concept_b,
            "hypothesis": raw,
            "model_id": self.model_id,
            "prompt_tokens": response.usage.input_tokens,
            "completion_tokens": response.usage.output_tokens,
            "cost_usd": cost,
        }

    def _build_bridge_prompt(
        self,
        concept_a: str,
        concept_b: str,
        papers_a: list[dict],
        papers_b: list[dict],
        graph_paths: list[dict] | None,
        similar_papers: list[dict] | None,
    ) -> str:
        def fmt_papers(papers: list[dict]) -> str:
            lines = []
            for p in papers[:5]:
                lines.append(f"- {p.get('title', 'Unknown')}")
                findings = p.get("key_findings") or []
                if isinstance(findings, str):
                    findings = json.loads(findings)
                if findings:
                    lines.append(f"  Finding: {findings[0][:200]}")
            return "\n".join(lines) or "No papers found"

        path_str = ""
        if graph_paths:
            paths_formatted = []
            for path in graph_paths[:3]:
                nodes = path.get("path_nodes", [])
                rels = path.get("rel_types", [])
                node_labels = []
                for n in nodes:
                    label = n.get("title") or n.get("text") or n.get("name") or "?"
                    node_labels.append(label[:40])
                if node_labels and rels:
                    path_str_parts = []
                    for i, node_label in enumerate(node_labels):
                        path_str_parts.append(node_label)
                        if i < len(rels):
                            path_str_parts.append(f"--[{rels[i]}]-->")
                    paths_formatted.append(" ".join(path_str_parts))
            if paths_formatted:
                path_str = "\n\nGraph paths found:\n" + "\n".join(paths_formatted)

        similar_str = ""
        if similar_papers:
            titles = [p.get("title", "")[:80] for p in similar_papers[:5]]
            similar_str = "\n\nSemantically bridging papers:\n" + "\n".join(f"- {t}" for t in titles if t)

        return f"""You are a scientific hypothesis generator. Your task is to find or construct the connection between two biomedical concepts using evidence from the literature.

CONCEPT A: {concept_a}
CONCEPT B: {concept_b}

Papers related to Concept A:
{fmt_papers(papers_a)}

Papers related to Concept B:
{fmt_papers(papers_b)}
{path_str}
{similar_str}

Generate a detailed bridge hypothesis that:
1. States the hypothesized connection between {concept_a} and {concept_b}
2. Explains the mechanistic pathway or logical chain linking them
3. Cites the specific papers/findings that support each step
4. Rates the strength of evidence (strong/moderate/weak/speculative)
5. Suggests the most promising experiment to test this connection

Format your response as:
**BRIDGE HYPOTHESIS**
[One sentence stating the connection]

**MECHANISTIC PATHWAY**
[Step-by-step mechanism]

**SUPPORTING EVIDENCE**
[Key papers and findings]

**EVIDENCE STRENGTH**: [strong/moderate/weak/speculative]

**SUGGESTED EXPERIMENT**
[Most direct test of this hypothesis]"""
