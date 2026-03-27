"""Pearl graph query tool — Neo4j connectome queries for Pearl facilitation.

Exposes a query_connectome function that Pearl can call to:
  - Find connections between concepts
  - Traverse mechanism pathways
  - Discover bridge papers linking disparate fields
  - Find entities related to a concept
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger("decoded.pearl.graph_tool")


def _get_neo4j_driver():
    from neo4j import GraphDatabase
    uri = os.environ.get("NEO4J_URI", "bolt://localhost:7687")
    user = os.environ.get("NEO4J_USER", "neo4j")
    password = os.environ.get("NEO4J_PASSWORD", "password")
    return GraphDatabase.driver(uri, auth=(user, password))


def query_connectome(
    question: str,
    concept_a: str | None = None,
    concept_b: str | None = None,
    query_type: str = "bridge",
    max_results: int = 10,
) -> dict[str, Any]:
    """Query the literature connectome graph.

    Args:
        question: Natural language description of what to find.
        concept_a: First concept/entity (for bridge queries).
        concept_b: Second concept/entity (for bridge queries).
        query_type: "bridge" | "neighbors" | "pathway" | "papers"
        max_results: Max results to return.

    Returns:
        dict with query results structured for Pearl's use.
    """
    try:
        driver = _get_neo4j_driver()
        driver.verify_connectivity()
    except Exception as e:
        logger.warning("Neo4j unavailable: %s", e)
        return _fallback_postgres_query(question, concept_a, concept_b, max_results)

    with driver.session() as session:
        if query_type == "bridge" and concept_a and concept_b:
            return _bridge_query(session, concept_a, concept_b, max_results)
        elif query_type == "neighbors" and concept_a:
            return _neighbors_query(session, concept_a, max_results)
        elif query_type == "pathway" and concept_a:
            return _pathway_query(session, concept_a, max_results)
        else:
            return _text_search_query(session, question, max_results)


def _bridge_query(session, concept_a: str, concept_b: str, max_results: int) -> dict:
    """Find papers and paths connecting two concepts."""
    # Find entities matching each concept
    result_a = session.run(
        """
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower($concept)
           OR toLower(e.text) CONTAINS toLower($concept)
        RETURN e.name AS name, e.entity_type AS type
        LIMIT 5
        """,
        concept=concept_a,
    )
    entities_a = [dict(r) for r in result_a]

    result_b = session.run(
        """
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower($concept)
           OR toLower(e.text) CONTAINS toLower($concept)
        RETURN e.name AS name, e.entity_type AS type
        LIMIT 5
        """,
        concept=concept_b,
    )
    entities_b = [dict(r) for r in result_b]

    # Find papers that mention both concepts
    result_papers = session.run(
        """
        MATCH (p:Paper)-[:HAS_ENTITY]->(ea:Entity),
              (p)-[:HAS_ENTITY]->(eb:Entity)
        WHERE (toLower(ea.name) CONTAINS toLower($concept_a)
               OR toLower(ea.text) CONTAINS toLower($concept_a))
          AND (toLower(eb.name) CONTAINS toLower($concept_b)
               OR toLower(eb.text) CONTAINS toLower($concept_b))
        RETURN p.paper_id AS paper_id, p.title AS title, p.journal AS journal,
               p.published_date AS published_date, p.doi AS doi
        LIMIT $limit
        """,
        concept_a=concept_a,
        concept_b=concept_b,
        limit=max_results,
    )
    bridge_papers = [dict(r) for r in result_papers]

    # Find connecting mechanisms
    result_mechs = session.run(
        """
        MATCH (m:Mechanism)
        WHERE toLower(m.description) CONTAINS toLower($concept_a)
          AND toLower(m.description) CONTAINS toLower($concept_b)
        RETURN m.description AS description, m.pathway AS pathway,
               m.upstream_entity AS upstream, m.downstream_entity AS downstream
        LIMIT $limit
        """,
        concept_a=concept_a,
        concept_b=concept_b,
        limit=max_results // 2,
    )
    mechanisms = [dict(r) for r in result_mechs]

    # Find discovered connections
    result_conns = session.run(
        """
        MATCH (c:Connection)
        WHERE (toLower(c.entity_a) CONTAINS toLower($concept_a)
               OR toLower(c.entity_b) CONTAINS toLower($concept_a))
          AND (toLower(c.entity_a) CONTAINS toLower($concept_b)
               OR toLower(c.entity_b) CONTAINS toLower($concept_b))
        RETURN c.entity_a AS entity_a, c.entity_b AS entity_b,
               c.connection_type AS connection_type,
               c.confidence AS confidence, c.hypothesis AS hypothesis
        ORDER BY c.confidence DESC
        LIMIT $limit
        """,
        concept_a=concept_a,
        concept_b=concept_b,
        limit=max_results // 2,
    )
    connections = [dict(r) for r in result_conns]

    return {
        "query_type": "bridge",
        "concept_a": concept_a,
        "concept_b": concept_b,
        "entities_a": entities_a,
        "entities_b": entities_b,
        "bridge_papers": bridge_papers,
        "mechanisms": mechanisms,
        "discovered_connections": connections,
        "summary": _summarize_bridge(concept_a, concept_b, bridge_papers, mechanisms, connections),
    }


def _neighbors_query(session, concept: str, max_results: int) -> dict:
    """Find entities and papers related to a concept."""
    result = session.run(
        """
        MATCH (e:Entity)
        WHERE toLower(e.name) CONTAINS toLower($concept)
           OR toLower(e.text) CONTAINS toLower($concept)
        OPTIONAL MATCH (e)<-[:HAS_ENTITY]-(p:Paper)
        RETURN e.name AS entity, e.entity_type AS entity_type,
               count(p) AS paper_count
        ORDER BY paper_count DESC
        LIMIT $limit
        """,
        concept=concept,
        limit=max_results,
    )
    entities = [dict(r) for r in result]

    result_claims = session.run(
        """
        MATCH (cl:Claim)
        WHERE toLower(cl.text) CONTAINS toLower($concept)
           OR toLower(cl.subject) CONTAINS toLower($concept)
           OR toLower(cl.object) CONTAINS toLower($concept)
        RETURN cl.text AS text, cl.claim_type AS claim_type,
               cl.evidence_strength AS evidence_strength,
               cl.subject AS subject, cl.predicate AS predicate, cl.object AS object
        LIMIT $limit
        """,
        concept=concept,
        limit=max_results,
    )
    claims = [dict(r) for r in result_claims]

    return {
        "query_type": "neighbors",
        "concept": concept,
        "entities": entities,
        "claims": claims,
        "summary": f"Found {len(entities)} related entities and {len(claims)} claims about '{concept}'.",
    }


def _pathway_query(session, concept: str, max_results: int) -> dict:
    """Find mechanisms and pathways involving a concept."""
    result = session.run(
        """
        MATCH (m:Mechanism)
        WHERE toLower(m.description) CONTAINS toLower($concept)
           OR toLower(m.upstream_entity) CONTAINS toLower($concept)
           OR toLower(m.downstream_entity) CONTAINS toLower($concept)
           OR toLower(m.pathway) CONTAINS toLower($concept)
        RETURN m.description AS description, m.pathway AS pathway,
               m.upstream_entity AS upstream, m.downstream_entity AS downstream,
               m.interaction_type AS interaction, m.context AS context
        LIMIT $limit
        """,
        concept=concept,
        limit=max_results,
    )
    mechanisms = [dict(r) for r in result]

    return {
        "query_type": "pathway",
        "concept": concept,
        "mechanisms": mechanisms,
        "summary": f"Found {len(mechanisms)} mechanisms involving '{concept}'.",
    }


def _text_search_query(session, question: str, max_results: int) -> dict:
    """General text search across all node types."""
    words = question.split()[:5]  # Use first 5 words
    search_term = " ".join(words)

    result = session.run(
        """
        MATCH (p:Paper)
        WHERE toLower(p.title) CONTAINS toLower($term)
           OR toLower(p.abstract) CONTAINS toLower($term)
        RETURN p.paper_id AS paper_id, p.title AS title,
               p.journal AS journal, p.published_date AS published_date
        LIMIT $limit
        """,
        term=search_term,
        limit=max_results,
    )
    papers = [dict(r) for r in result]

    return {
        "query_type": "text_search",
        "question": question,
        "papers": papers,
        "summary": f"Found {len(papers)} papers matching '{search_term}'.",
    }


def _fallback_postgres_query(
    question: str,
    concept_a: str | None,
    concept_b: str | None,
    max_results: int,
) -> dict:
    """Fallback: query PostgreSQL when Neo4j is unavailable."""
    import psycopg2
    import psycopg2.extras

    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    results = {"query_type": "fallback_postgres", "question": question}

    if concept_a and concept_b:
        cur.execute(
            """
            SELECT title, doi, journal, published_date,
                   abstract
            FROM raw_papers
            WHERE (title ILIKE %s OR abstract ILIKE %s)
              AND (title ILIKE %s OR abstract ILIKE %s)
            ORDER BY published_date DESC NULLS LAST
            LIMIT %s
            """,
            (f"%{concept_a}%", f"%{concept_a}%",
             f"%{concept_b}%", f"%{concept_b}%",
             max_results),
        )
        papers = [dict(r) for r in cur.fetchall()]

        # Also check kb_entries for any bridged claims
        cur.execute(
            """
            SELECT title, content, operation, density, confidence
            FROM kb_entries
            WHERE workstation = 'decoded_connectome'
              AND (content ILIKE %s OR title ILIKE %s)
              AND (content ILIKE %s OR title ILIKE %s)
            ORDER BY created_at DESC
            LIMIT %s
            """,
            (f"%{concept_a}%", f"%{concept_a}%",
             f"%{concept_b}%", f"%{concept_b}%",
             max_results),
        )
        kb_entries = [dict(r) for r in cur.fetchall()]

        results.update({
            "concept_a": concept_a,
            "concept_b": concept_b,
            "bridge_papers": [
                {
                    "title": p["title"],
                    "doi": p.get("doi"),
                    "journal": p.get("journal"),
                    "abstract_snippet": (p.get("abstract") or "")[:200],
                }
                for p in papers
            ],
            "kb_entries": kb_entries,
            "summary": (
                f"Neo4j unavailable. Found {len(papers)} papers and {len(kb_entries)} "
                f"KB entries mentioning both '{concept_a}' and '{concept_b}' (PostgreSQL fallback)."
            ),
        })
    else:
        term = concept_a or question
        cur.execute(
            """
            SELECT title, doi, journal, published_date
            FROM raw_papers
            WHERE title ILIKE %s OR abstract ILIKE %s
            ORDER BY published_date DESC NULLS LAST
            LIMIT %s
            """,
            (f"%{term}%", f"%{term}%", max_results),
        )
        papers = [dict(r) for r in cur.fetchall()]
        results.update({
            "papers": papers,
            "summary": f"Found {len(papers)} papers matching '{term}' (PostgreSQL fallback).",
        })

    conn.close()
    return results


def _summarize_bridge(
    concept_a: str,
    concept_b: str,
    papers: list,
    mechanisms: list,
    connections: list,
) -> str:
    parts = []
    if papers:
        parts.append(f"{len(papers)} paper(s) directly bridge '{concept_a}' and '{concept_b}'")
    if mechanisms:
        parts.append(f"{len(mechanisms)} mechanism(s) connect them")
    if connections:
        parts.append(f"{len(connections)} discovered connection(s) found")
    if not parts:
        return f"No direct connections found between '{concept_a}' and '{concept_b}' in the current connectome."
    return "In the connectome: " + "; ".join(parts) + "."
