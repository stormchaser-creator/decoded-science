"""AI Chat — multi-model paper Q&A with full corpus RAG.

Supports: Claude Sonnet, Claude Haiku, GPT-4o, Grok-3.
Context includes: paper data, connections, brief, and corpus search results.
"""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from typing import Any, AsyncGenerator

from dotenv import load_dotenv
load_dotenv(Path(__file__).resolve().parent.parent.parent / ".env", override=True)

import psycopg2
import psycopg2.extras

from decoded.cost_tracker import calculate_cost, MODEL_PRICING

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Model registry
# ---------------------------------------------------------------------------

MODELS = {
    "claude-sonnet-4-6": {
        "provider": "anthropic",
        "label": "Claude Sonnet",
        "description": "Best for deep scientific analysis",
    },
    "claude-haiku-4-5-20251001": {
        "provider": "anthropic",
        "label": "Claude Haiku",
        "description": "Fast & cheap for quick questions",
    },
    "gpt-4o": {
        "provider": "openai",
        "label": "GPT-4o",
        "description": "OpenAI's flagship model",
    },
    "grok-3": {
        "provider": "xai",
        "label": "Grok 3",
        "description": "xAI's reasoning model",
    },
}

# ---------------------------------------------------------------------------
# Paper context builder
# ---------------------------------------------------------------------------


def build_paper_context(conn, paper_id: str) -> dict[str, Any]:
    """Gather all data about a paper for chat context."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # Paper + extraction
    cur.execute("""
        SELECT p.id, p.title, p.abstract, p.authors, p.journal, p.doi,
               p.published_date, p.data_source, p.status,
               e.entities, e.claims, e.mechanisms, e.key_findings,
               e.study_design, e.population, e.primary_outcome,
               e.sample_size, e.limitations
        FROM raw_papers p
        LEFT JOIN extraction_results e ON e.paper_id = p.id
        WHERE p.id = %s
    """, (paper_id,))
    paper = cur.fetchone()
    if not paper:
        return {}

    # Connections (top 20 by confidence)
    cur.execute("""
        SELECT dc.connection_type, dc.description, dc.confidence,
               CASE WHEN dc.paper_a_id = %s THEN pb.title ELSE pa.title END AS connected_title,
               CASE WHEN dc.paper_a_id = %s THEN dc.paper_b_id ELSE dc.paper_a_id END AS connected_id
        FROM discovered_connections dc
        LEFT JOIN raw_papers pa ON pa.id = dc.paper_a_id
        LEFT JOIN raw_papers pb ON pb.id = dc.paper_b_id
        WHERE dc.paper_a_id = %s OR dc.paper_b_id = %s
        ORDER BY dc.confidence DESC
        LIMIT 20
    """, (paper_id, paper_id, paper_id, paper_id))
    connections = [dict(r) for r in cur.fetchall()]

    # Intelligence brief
    cur.execute("""
        SELECT overall_quality, summary, strengths, weaknesses, red_flags,
               recommendation, methodology_score, novelty_score, brief_confidence
        FROM paper_critiques
        WHERE paper_id = %s AND brief_confidence != 'insufficient'
        ORDER BY created_at DESC LIMIT 1
    """, (paper_id,))
    critique = cur.fetchone()

    return {
        "paper": dict(paper),
        "connections": connections,
        "critique": dict(critique) if critique else None,
    }


def build_system_prompt(context: dict) -> str:
    """Build the system prompt with full paper context."""
    paper = context.get("paper", {})
    connections = context.get("connections", [])
    critique = context.get("critique")

    # Format entities
    entities_raw = paper.get("entities") or []
    if isinstance(entities_raw, str):
        try:
            entities_raw = json.loads(entities_raw)
        except Exception:
            entities_raw = []
    entity_names = []
    for e in entities_raw[:30]:
        if isinstance(e, dict):
            entity_names.append(e.get("name", str(e)))
        else:
            entity_names.append(str(e))

    # Format claims
    claims_raw = paper.get("claims") or []
    if isinstance(claims_raw, str):
        try:
            claims_raw = json.loads(claims_raw)
        except Exception:
            claims_raw = []
    claim_texts = []
    for c in claims_raw[:15]:
        if isinstance(c, dict):
            claim_texts.append(c.get("claim", c.get("text", str(c))))
        else:
            claim_texts.append(str(c))

    # Format key findings
    findings_raw = paper.get("key_findings") or []
    if isinstance(findings_raw, str):
        try:
            findings_raw = json.loads(findings_raw)
        except Exception:
            findings_raw = []

    # Format connections
    conn_lines = []
    for c in connections:
        conn_lines.append(
            f"  - [{c['connection_type'].upper()}] {c['connected_title']}: "
            f"{c['description'] or 'No description'} (conf: {c['confidence']:.0%})"
        )

    # Format authors
    authors = paper.get("authors") or []
    if isinstance(authors, str):
        try:
            authors = json.loads(authors)
        except Exception:
            authors = [authors]
    author_str = ", ".join(
        (a if isinstance(a, str) else a.get("name", str(a)))
        for a in authors[:5]
    )
    if len(authors) > 5:
        author_str += f" et al. ({len(authors)} total)"

    # Format brief
    brief_section = ""
    if critique:
        strengths = critique.get("strengths") or []
        if isinstance(strengths, str):
            try:
                strengths = json.loads(strengths)
            except Exception:
                strengths = [strengths]
        weaknesses = critique.get("weaknesses") or []
        if isinstance(weaknesses, str):
            try:
                weaknesses = json.loads(weaknesses)
            except Exception:
                weaknesses = [weaknesses]

        brief_section = f"""
INTELLIGENCE BRIEF:
  Quality: {critique.get('overall_quality', 'unknown')} | Recommendation: {critique.get('recommendation', 'unknown')}
  Methodology: {critique.get('methodology_score', '?')}/10 | Novelty: {critique.get('novelty_score', '?')}/10
  Summary: {critique.get('summary', 'Not available')}
  Strengths: {'; '.join(str(s) for s in strengths[:3])}
  Weaknesses: {'; '.join(str(w) for w in weaknesses[:3])}
"""

    return f"""You are a research analyst for The Decoded Human, a literature connectome that maps relationships between biomedical research papers. The user is viewing a specific paper and asking questions about it.

You have access to the paper's full data, its connections to other papers in the corpus, and its intelligence brief. Use ALL of this context to give insightful, specific answers. When relevant, cite connected papers by name. Be direct and scientific.

CURRENT PAPER:
  Title: {paper.get('title', 'Unknown')}
  Authors: {author_str}
  Journal: {paper.get('journal', 'Unknown')} ({paper.get('published_date', 'Unknown')})
  DOI: {paper.get('doi', 'Not available')}
  Data source: {paper.get('data_source', 'unknown')}
  Study design: {paper.get('study_design', 'Unknown')}
  Population: {paper.get('population', 'Unknown')}
  Sample size: {paper.get('sample_size', 'Unknown')}
  Primary outcome: {paper.get('primary_outcome', 'Unknown')}

ABSTRACT:
{paper.get('abstract', 'Not available')}

KEY FINDINGS:
{chr(10).join(f'  - {f}' for f in findings_raw[:10]) if findings_raw else '  Not extracted'}

ENTITIES ({len(entity_names)}):
  {', '.join(entity_names) if entity_names else 'None extracted'}

CLAIMS ({len(claim_texts)}):
{chr(10).join(f'  - {c}' for c in claim_texts) if claim_texts else '  None extracted'}

CONNECTIONS TO OTHER PAPERS ({len(connections)}):
{chr(10).join(conn_lines) if conn_lines else '  No connections found'}
{brief_section}
CORPUS INFO: The Decoded Human corpus contains 18,000+ papers focused on aging, longevity, neurodegeneration, and related biomedical research. Connections are AI-discovered relationships between papers.

Answer the user's questions using this context. Be specific — reference connected papers by name when relevant. If asked about something not in the context, say so honestly."""


# ---------------------------------------------------------------------------
# Corpus search (RAG)
# ---------------------------------------------------------------------------


def search_corpus(conn, query: str, limit: int = 10) -> list[dict]:
    """Search the full corpus for papers matching a query. Used for RAG."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    try:
        cur.execute("""
            SELECT id, title, abstract, journal, published_date, data_source,
                   ts_rank(search_vector, websearch_to_tsquery('english', %s)) AS rank
            FROM raw_papers
            WHERE search_vector @@ websearch_to_tsquery('english', %s)
            ORDER BY rank DESC
            LIMIT %s
        """, (query, query, limit))
        return [dict(r) for r in cur.fetchall()]
    except Exception:
        # Fallback to ILIKE if full-text search fails
        cur.execute("""
            SELECT id, title, abstract, journal, published_date, data_source
            FROM raw_papers
            WHERE title ILIKE %s OR abstract ILIKE %s
            ORDER BY published_date DESC NULLS LAST
            LIMIT %s
        """, (f"%{query}%", f"%{query}%", limit))
        return [dict(r) for r in cur.fetchall()]


# ---------------------------------------------------------------------------
# Streaming adapters
# ---------------------------------------------------------------------------


def stream_anthropic(model: str, system: str, messages: list[dict]) -> tuple:
    """Stream from Anthropic API. Yields (chunks, usage_dict)."""
    import anthropic
    client = anthropic.Anthropic()

    with client.messages.stream(
        model=model,
        max_tokens=2048,
        system=system,
        messages=messages,
    ) as stream:
        for text in stream.text_stream:
            yield {"delta": text}

        # After stream ends, get final message for usage
        msg = stream.get_final_message()
        cost = calculate_cost(model, msg.usage.input_tokens, msg.usage.output_tokens)
        yield {
            "done": True,
            "usage": {
                "input_tokens": msg.usage.input_tokens,
                "output_tokens": msg.usage.output_tokens,
                "model": model,
            },
            "cost_usd": round(cost, 4),
        }


def stream_openai(model: str, system: str, messages: list[dict], base_url: str | None = None) -> tuple:
    """Stream from OpenAI-compatible API (GPT-4o, Grok). Yields chunks."""
    import openai

    kwargs = {}
    if base_url:
        kwargs["base_url"] = base_url
        kwargs["api_key"] = os.environ.get("XAI_API_KEY", "")
    else:
        kwargs["api_key"] = os.environ.get("OPENAI_API_KEY", "")

    client = openai.OpenAI(**kwargs)

    oai_messages = [{"role": "system", "content": system}]
    for m in messages:
        oai_messages.append({"role": m["role"], "content": m["content"]})

    total_completion = 0
    stream = client.chat.completions.create(
        model=model,
        messages=oai_messages,
        max_tokens=2048,
        stream=True,
        stream_options={"include_usage": True},
    )

    input_tokens = 0
    output_tokens = 0
    for chunk in stream:
        if chunk.usage:
            input_tokens = chunk.usage.prompt_tokens or 0
            output_tokens = chunk.usage.completion_tokens or 0
        if chunk.choices and chunk.choices[0].delta.content:
            yield {"delta": chunk.choices[0].delta.content}
            total_completion += 1

    # Estimate cost
    pricing = MODEL_PRICING.get(model)
    if pricing:
        cost = calculate_cost(model, input_tokens, output_tokens)
    else:
        # Rough estimate for unknown models
        cost = (input_tokens / 1_000_000 * 3.0) + (output_tokens / 1_000_000 * 15.0)

    yield {
        "done": True,
        "usage": {
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "model": model,
        },
        "cost_usd": round(cost, 4),
    }


def stream_chat(model: str, system: str, messages: list[dict]):
    """Dispatch to the correct provider and stream responses."""
    info = MODELS.get(model)
    if not info:
        yield {"error": f"Unknown model: {model}"}
        return

    provider = info["provider"]
    try:
        if provider == "anthropic":
            yield from stream_anthropic(model, system, messages)
        elif provider == "openai":
            yield from stream_openai(model, system, messages)
        elif provider == "xai":
            yield from stream_openai(
                model, system, messages,
                base_url="https://api.x.ai/v1"
            )
        else:
            yield {"error": f"Unknown provider: {provider}"}
    except Exception as exc:
        logger.exception("Chat stream error for model %s", model)
        yield {"error": str(exc)}
