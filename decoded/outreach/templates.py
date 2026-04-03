"""Email template system for author outreach.

Emails come from Dr. Eric Whitney, DO — board-certified neurosurgeon and
researcher reaching out as a genuine peer with a discovered finding.

Five-part structure (per Eric's spec):
  1. Thankful   — genuine gratitude for their specific work
  2. Impact     — where their work is making an impact in the research landscape
  3. Why it matters — bigger-picture significance of their contribution
  4. The connection — the specific discovered connection, clearly stated
  5. Why it's important — significance of this connection for advancing understanding

Every email:
  - Discloses AI involvement in the first paragraph
  - Links to thedecodedhuman.com for the visualized connection
  - Is concise (3–4 short paragraphs, under 300 words)
  - Has a warm, collegial researcher-to-researcher tone
  - Does NOT use "MD" — Eric is a DO (Doctor of Osteopathic Medicine)
"""

from __future__ import annotations

import json
import logging
from typing import Any

import anthropic

from decoded.cost_tracker import calculate_cost

logger = logging.getLogger(__name__)

TEMPLATE_MODEL = "claude-sonnet-4-6"

SENDER_NAME = "Dr. Eric Whitney, DO"
SENDER_EMAIL = "Drericwhitney@gmail.com"
SITE_URL = "https://thedecodedhuman.com"


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
        sender_name: str = SENDER_NAME,
        sender_email: str = SENDER_EMAIL,
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

        subject, body = self._parse_email(raw)

        logger.info("Generated email for %s | cost $%.4f", author_name, cost)

        return {
            "to_name": author_name or "Researcher",
            "to_email": author_email,
            "subject": subject,
            "body": body,
            "paper_id": str(paper.get("id", "")),
            "connection_id": str(connection.get("id", "")),
            "paper_b_id": str(connected_paper.get("id", "")),
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
        finding_str = findings[0][:250] if findings else paper.get("abstract", "")[:250]

        connected_findings = connected_paper.get("key_findings") or []
        if isinstance(connected_findings, str):
            connected_findings = json.loads(connected_findings)
        connected_finding_str = connected_findings[0][:250] if connected_findings else connected_paper.get("abstract", "")[:250]

        conn_type_phrase = CONNECTION_TYPE_PHRASES.get(
            connection.get("connection_type", "default"),
            "connects to"
        )

        paper_title = paper.get("title", "your paper")
        connected_title = connected_paper.get("title", "a related paper")
        confidence_pct = connection.get("confidence", 0)
        conn_description = connection.get("description", "")
        conn_type = connection.get("connection_type", "convergent_evidence")

        return f"""You are writing a personalized outreach email on behalf of Dr. Eric Whitney, DO — a board-certified neurosurgeon and researcher who runs The Decoded Human, a literature connectome that uses AI to map connections across biomedical research.

SENDER: {sender_name} (DO — Doctor of Osteopathic Medicine, NEVER "MD")
SENDER EMAIL: {SENDER_EMAIL}
SITE: {SITE_URL}

VOICE REFERENCE: The approved gold-standard email is the one sent to Esra Capanoglu (re: antinutrients / Fanconi anemia aging hallmarks) — Eric called it "strong, very well written, perfect on tone." Match that voice exactly. Key qualities: specific rather than generic, honest about AI, clinically grounded, warm but not flattering, intellectually curious.

RECIPIENT FIRST NAME: {first_name}

RECIPIENT'S PAPER:
Title: {paper_title}
Key finding: {finding_str}

CONNECTED PAPER:
Title: {connected_title}
Key finding: {connected_finding_str}

CONNECTION TYPE: {conn_type}
CONNECTION PHRASE: {conn_type_phrase}
CONNECTION DESCRIPTION: {conn_description}
AI CONFIDENCE: {confidence_pct:.0%}

REQUIRED FIVE-PART EMAIL STRUCTURE:

1. THANKFUL — Open with genuine, specific gratitude for their research contribution.
   Reference something specific from their paper (a specific finding, argument, framing,
   or methodological approach — not just the topic). Disclose AI in this first paragraph:
   mention that The Decoded Human uses AI to map connections across the literature, and
   that's how this email came to be written.

2. IMPACT — Show where their work is making an impact. Describe how their specific
   findings fit into the broader research landscape. Be concrete about what their paper
   uniquely adds. Show you actually understood their contribution — no generic praise.

3. WHY IT MATTERS — Explain the bigger-picture significance. Connect their work to
   patient outcomes, clinical translation, or fundamental biological understanding.
   Speak as a neurosurgeon-researcher who sees why this matters. Grounded — no hype.

4. THE CONNECTION — Present the specific AI-discovered connection between their paper
   and "{connected_title}". State the connection type ({conn_type_phrase}) and what
   exactly the connection is, in plain language. Include the link: {SITE_URL}/connections.
   Be intellectually honest: state the confidence level ({confidence_pct:.0%}) and
   explicitly note this is an AI-generated observation, not a peer-reviewed finding.

5. WHY IT'S IMPORTANT — Explain what this connection could mean for future research.
   What questions does it open that weren't visible before? Close with:
   "I'd love to hear your thoughts on this." — genuine curiosity, not a request.

ABSOLUTE REQUIREMENTS:
- Warm, collegial, researcher-to-researcher tone — not marketing
- Under 300 words total (body only, excluding sign-off and footer)
- Every compliment must reference specifics from their actual paper
- No marketing language, no asks, no collaboration requests in first email
- DO NOT say "game-changing", "revolutionary", "groundbreaking", "paradigm shift"
- Confidence level must be stated explicitly in paragraph 4

SIGN-OFF (use exactly):
Warm regards,
Dr. Eric Whitney, DO
drericwhitney@gmail.com
{SITE_URL}

FOOTER (include exactly, after blank line and ---):
---
To unsubscribe from future research notes, reply with "unsubscribe" in the subject.

FORMAT YOUR RESPONSE EXACTLY AS:
SUBJECT: [subject line — specific to this paper and connection, not generic]

BODY:
[email body following the five-part structure above, including sign-off and footer]"""

    def _parse_email(self, raw: str) -> tuple[str, str]:
        """Parse subject and body from the LLM response."""
        lines = raw.strip().split("\n")
        subject = ""
        body_lines = []
        in_body = False

        for line in lines:
            if line.upper().startswith("SUBJECT:"):
                subject = line.split(":", 1)[1].strip()
            elif line.upper().startswith("BODY:"):
                in_body = True
            elif in_body:
                body_lines.append(line)

        # Fallback: first line as subject, rest as body
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
    sender_name: str = SENDER_NAME,
) -> dict[str, str]:
    """Generate a basic outreach email without LLM (deterministic, for testing)."""
    contact = paper.get("contact") or {}
    author_name = contact.get("corresponding_author") or "Researcher"
    first_name = _first_author_first_name(author_name)
    conn_type = connection.get("connection_type", "connects to")
    conn_phrase = CONNECTION_TYPE_PHRASES.get(conn_type, "connects to")

    paper_title = _truncate(paper.get("title"), 90)
    connected_title = _truncate(connected_paper.get("title"), 90)
    conn_description = connection.get("description", "The papers share significant biological overlap.")

    subject = f"A connection discovered in your research on {_truncate(paper.get('title'), 50)}"

    body = f"""Dear {first_name},

I'm writing to share something that emerged from The Decoded Human — a literature connectome I run that uses AI to map connections across biomedical research. Your paper "{paper_title}" caught our system's attention, and I wanted to reach out personally.

Your work makes a meaningful contribution to this area of research. The findings are exactly the kind of rigorous, specific contribution that advances our collective understanding — and that's precisely why it surfaced in our analysis.

In the broader context, work like yours matters because it provides the kind of grounded evidence the field needs to move forward. We've indexed thousands of papers, and yours stands out for the specificity of its contribution.

What's particularly interesting: our system discovered that your paper {conn_phrase} "{connected_title}". {conn_description} You can see this connection visualized at {SITE_URL}/connections.

This connection could be significant for future research directions in this area. I'd love to hear your thoughts on whether this resonates with your own sense of where the field is heading.

Warmly,
{sender_name}
The Decoded Human | {SITE_URL}

---
To unsubscribe from future notes, reply with "unsubscribe" in the subject line."""

    return {
        "to_name": author_name,
        "to_email": contact.get("email"),
        "subject": subject,
        "body": body,
        "paper_id": str(paper.get("id", "")),
        "connection_id": str(connection.get("id", "")),
        "paper_b_id": str(connected_paper.get("id", "")),
        "cost_usd": 0.0,
    }
