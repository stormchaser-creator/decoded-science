"""Email template system for author outreach.

Pearl-quality outreach: specific, value-first, AI disclosed in first paragraph.
Templates adapt based on connection type and paper content.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from decoded.cost_tracker import calculate_cost

logger = logging.getLogger(__name__)

TEMPLATE_MODEL = "claude-sonnet-4-6"


# ---------------------------------------------------------------------------
# Static template helpers
# ---------------------------------------------------------------------------

CONNECTION_TYPE_PHRASES = {
    "replicates": "appears to replicate",
    "contradicts": "presents findings that may contradict",
    "extends": "builds directly on",
    "mechanism_for": "may explain the mechanism underlying findings in",
    "shares_target": "investigates overlapping biological targets with",
    "convergent_evidence": "converges on similar findings as",
    "methodological_parallel": "uses a closely parallel methodology to",
    "meta_analysis_of": "synthesizes findings that include",
}

SUBJECT_TEMPLATES = {
    "convergent_evidence": "Your work on {topic_a} may connect to {topic_b}",
    "mechanism_for": "Possible mechanistic link between your work and {connected_paper_short}",
    "contradicts": "An interesting discrepancy between your findings and recent work",
    "extends": "Building on your {topic_a} findings — a potential connection",
    "default": "A discovered connection involving your recent research",
}


def _first_author_first_name(author: str | None) -> str:
    """Extract first name from 'Last, First' or 'First Last' format."""
    if not author:
        return "Dr."
    author = author.strip()
    if "," in author:
        parts = author.split(",", 1)
        first = parts[1].strip().split()[0] if parts[1].strip() else ""
    else:
        first = author.split()[0]
    return first or "Dr."


def _truncate(text: str | None, max_len: int = 80) -> str:
    if not text:
        return ""
    return text[:max_len] + "..." if len(text) > max_len else text


# ---------------------------------------------------------------------------
# LLM-generated outreach emails
# ---------------------------------------------------------------------------

class EmailTemplateGenerator:
    """Generate personalized author outreach emails using Claude Sonnet."""

    def __init__(self, model_id: str = TEMPLATE_MODEL):
        self.model_id = model_id
        self._client = anthropic.Anthropic()

    def generate(
        self,
        paper: dict[str, Any],
        connection: dict[str, Any],
        connected_paper: dict[str, Any],
        sender_name: str = "The Decoded Team",
        sender_email: str = "hello@decoded.ai",
    ) -> dict[str, str]:
        """Generate a personalized outreach email.

        Returns dict with 'subject', 'body', 'to_name', 'to_email'.
        """
        contact = paper.get("contact") or {}
        author_name = contact.get("corresponding_author") or (paper.get("authors") or [None])[-1]
        author_email = contact.get("email")
        first_name = _first_author_first_name(author_name)

        prompt = self._build_prompt(
            paper=paper,
            connection=connection,
            connected_paper=connected_paper,
            first_name=first_name,
            sender_name=sender_name,
        )

        response = self._client.messages.create(
            model=self.model_id,
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}],
        )

        raw = response.content[0].text
        cost = calculate_cost(
            self.model_id,
            response.usage.input_tokens,
            response.usage.output_tokens,
        )

        # Parse subject and body
        subject, body = self._parse_email(raw)

        logger.info("Generated email for %s | cost $%.4f", author_name, cost)

        return {
            "to_name": author_name or "Researcher",
            "to_email": author_email,
            "subject": subject,
            "body": body,
            "paper_id": str(paper.get("id", "")),
            "connection_id": str(connection.get("id", "")),
            "cost_usd": cost,
        }

    def _build_prompt(
        self,
        paper: dict,
        connection: dict,
        connected_paper: dict,
        first_name: str,
        sender_name: str,
    ) -> str:
        findings = paper.get("key_findings") or []
        if isinstance(findings, str):
            findings = json.loads(findings)
        finding_str = findings[0][:200] if findings else paper.get("abstract", "")[:200]

        connected_findings = connected_paper.get("key_findings") or []
        if isinstance(connected_findings, str):
            connected_findings = json.loads(connected_findings)
        connected_finding_str = connected_findings[0][:200] if connected_findings else connected_paper.get("abstract", "")[:200]

        conn_type_phrase = CONNECTION_TYPE_PHRASES.get(
            connection.get("connection_type", "default"),
            "connects to"
        )

        return f"""You are writing a personalized, thoughtful outreach email from a scientific research intelligence platform called Decoded.

CRITICAL REQUIREMENTS:
1. Disclose AI in the FIRST PARAGRAPH — Decoded uses AI to discover connections across the literature
2. Be specific about the actual scientific connection — no generic flattery
3. Lead with VALUE to the researcher, not what you want from them
4. Be concise (under 250 words)
5. Professional but warm tone — researcher to researcher
6. Do NOT ask for anything in the first email — just share the discovery
7. Include an unsubscribe note at the bottom

RECIPIENT'S PAPER:
Title: {paper.get('title', '')}
Key finding: {finding_str}

CONNECTED PAPER:
Title: {connected_paper.get('title', '')}
Key finding: {connected_finding_str}

CONNECTION TYPE: {connection.get('connection_type', '')}
CONNECTION DESCRIPTION: {connection.get('description', '')}
CONFIDENCE: {connection.get('confidence', 0):.0%}

SENDER: {sender_name}
RECIPIENT FIRST NAME: {first_name}

Write the email now. Format as:
SUBJECT: [subject line]

BODY:
[email body]"""

    def _parse_email(self, raw: str) -> tuple[str, str]:
        """Parse subject and body from the LLM response."""
        lines = raw.strip().split("\n")
        subject = ""
        body_lines = []
        in_body = False

        for i, line in enumerate(lines):
            if line.upper().startswith("SUBJECT:"):
                subject = line.split(":", 1)[1].strip()
            elif line.upper().startswith("BODY:"):
                in_body = True
            elif in_body:
                body_lines.append(line)

        # Fallback: just use first line as subject, rest as body
        if not subject and lines:
            subject = lines[0].replace("Subject:", "").replace("SUBJECT:", "").strip()
            body_lines = lines[2:] if len(lines) > 2 else lines[1:]

        body = "\n".join(body_lines).strip()
        return subject, body


# ---------------------------------------------------------------------------
# Plain text template (no LLM — for testing/fallback)
# ---------------------------------------------------------------------------

def generate_static_email(
    paper: dict[str, Any],
    connection: dict[str, Any],
    connected_paper: dict[str, Any],
    sender_name: str = "The Decoded Team",
) -> dict[str, str]:
    """Generate a basic outreach email without LLM (deterministic, for testing)."""
    contact = paper.get("contact") or {}
    author_name = contact.get("corresponding_author") or "Researcher"
    first_name = _first_author_first_name(author_name)
    conn_type = connection.get("connection_type", "connects to")
    conn_phrase = CONNECTION_TYPE_PHRASES.get(conn_type, "connects to")

    subject = f"AI-discovered connection: Your work {conn_phrase[:30]} recent research"

    body = f"""Dear {first_name},

I'm writing from Decoded, a research intelligence platform that uses AI to discover connections across the scientific literature. Our system surfaced an interesting link involving your recent work.

Your paper "{_truncate(paper.get('title'), 80)}" {conn_phrase} "{_truncate(connected_paper.get('title'), 80)}".

Specifically: {connection.get('description', 'The papers share significant biological overlap.')}

We thought you might find this connection useful for future research directions or grant applications. Decoded continuously maps relationships across thousands of papers in your field.

No action needed — we're just sharing this discovery. If you'd like to explore the full connection map for your research area, reply to this email and we'll set you up with access.

Warmly,
{sender_name}

---
This message was sent by Decoded's AI-powered literature monitoring system. To unsubscribe, reply with "unsubscribe" in the subject line."""

    return {
        "to_name": author_name,
        "to_email": contact.get("email"),
        "subject": subject,
        "body": body,
        "paper_id": str(paper.get("id", "")),
        "connection_id": str(connection.get("id", "")),
        "cost_usd": 0.0,
    }
