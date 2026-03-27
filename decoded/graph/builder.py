"""GraphBuilder: build Neo4j knowledge graph from extracted paper data.

Node types:   Paper, Researcher, Entity, Claim, Mechanism, Method
Relationship: AUTHORED_BY, HAS_ENTITY, MAKES_CLAIM, DESCRIBES_MECHANISM,
              USES_METHOD, CITES, CONNECTS
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

from neo4j import GraphDatabase, Driver

logger = logging.getLogger(__name__)

NEO4J_URI = "bolt://localhost:7687"
NEO4J_USER = "neo4j"
NEO4J_PASSWORD = "decoded123"


def _short_id(text: str) -> str:
    """Stable 12-char hex ID for deduplicating by canonical text."""
    return hashlib.sha1(text.lower().strip().encode()).hexdigest()[:12]


class GraphBuilder:
    """Build and populate the Neo4j knowledge graph.

    Args:
        uri: Neo4j bolt URI
        user: Neo4j username
        password: Neo4j password
    """

    def __init__(
        self,
        uri: str = NEO4J_URI,
        user: str = NEO4J_USER,
        password: str = NEO4J_PASSWORD,
    ):
        self._driver: Driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    def __enter__(self) -> "GraphBuilder":
        return self

    def __exit__(self, *_) -> None:
        self.close()

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    def ensure_constraints(self) -> None:
        """Create uniqueness constraints and indexes if not present."""
        constraints = [
            "CREATE CONSTRAINT paper_id IF NOT EXISTS FOR (p:Paper) REQUIRE p.id IS UNIQUE",
            "CREATE CONSTRAINT researcher_name IF NOT EXISTS FOR (r:Researcher) REQUIRE r.name IS UNIQUE",
            "CREATE CONSTRAINT entity_id IF NOT EXISTS FOR (e:Entity) REQUIRE e.id IS UNIQUE",
            "CREATE CONSTRAINT method_id IF NOT EXISTS FOR (m:Method) REQUIRE m.id IS UNIQUE",
        ]
        indexes = [
            "CREATE INDEX paper_doi IF NOT EXISTS FOR (p:Paper) ON (p.doi)",
            "CREATE INDEX paper_title IF NOT EXISTS FOR (p:Paper) ON (p.title)",
            "CREATE INDEX entity_type IF NOT EXISTS FOR (e:Entity) ON (e.entity_type)",
            "CREATE INDEX entity_text IF NOT EXISTS FOR (e:Entity) ON (e.text)",
            "CREATE INDEX method_name IF NOT EXISTS FOR (m:Method) ON (m.name)",
        ]
        with self._driver.session() as s:
            for stmt in constraints + indexes:
                try:
                    s.run(stmt)
                except Exception as exc:
                    logger.debug("Constraint/index already exists or error: %s", exc)

    # ------------------------------------------------------------------
    # Paper node
    # ------------------------------------------------------------------

    def upsert_paper(self, paper: dict[str, Any]) -> None:
        """Create or update a Paper node."""
        pub_date = None
        if paper.get("published_date"):
            pd = paper["published_date"]
            pub_date = pd.isoformat() if hasattr(pd, "isoformat") else str(pd)

        authors = paper.get("authors") or []
        if isinstance(authors, str):
            try:
                authors = json.loads(authors)
            except Exception:
                authors = [authors]

        with self._driver.session() as s:
            s.run(
                """
                MERGE (p:Paper {id: $id})
                SET p.title       = $title,
                    p.doi         = $doi,
                    p.journal     = $journal,
                    p.source      = $source,
                    p.pub_date    = $pub_date,
                    p.abstract    = $abstract,
                    p.status      = $status,
                    p.updated_at  = timestamp()
                """,
                id=str(paper["id"]),
                title=paper.get("title", ""),
                doi=paper.get("doi"),
                journal=paper.get("journal"),
                source=paper.get("source", "unknown"),
                pub_date=pub_date,
                abstract=(paper.get("abstract") or "")[:500],
                status=paper.get("status", "unknown"),
            )

            # Researcher nodes + AUTHORED_BY edges
            for author in authors[:20]:  # cap at 20 authors per paper
                if not author or not author.strip():
                    continue
                s.run(
                    """
                    MERGE (r:Researcher {name: $name})
                    WITH r
                    MATCH (p:Paper {id: $paper_id})
                    MERGE (p)-[:AUTHORED_BY]->(r)
                    """,
                    name=author.strip(),
                    paper_id=str(paper["id"]),
                )

    # ------------------------------------------------------------------
    # Extraction data
    # ------------------------------------------------------------------

    def upsert_extraction(self, paper_id: str, extraction: dict[str, Any]) -> dict[str, int]:
        """Add Entity, Claim, Mechanism, Method nodes from extraction data."""
        counts = {"entities": 0, "claims": 0, "mechanisms": 0, "methods": 0}

        def _load(val) -> list:
            if isinstance(val, list):
                return val
            if isinstance(val, str):
                try:
                    return json.loads(val)
                except Exception:
                    return []
            return []

        entities = _load(extraction.get("entities"))
        claims = _load(extraction.get("claims"))
        mechanisms = _load(extraction.get("mechanisms"))
        methods = _load(extraction.get("methods"))

        with self._driver.session() as s:
            # Entities — deduplicate by (normalized text, type)
            for ent in entities:
                text = (ent.get("text") or "").strip()
                etype = (ent.get("entity_type") or "unknown").lower()
                if not text:
                    continue
                eid = _short_id(f"{etype}:{text}")
                s.run(
                    """
                    MERGE (e:Entity {id: $id})
                    SET e.text        = $text,
                        e.entity_type = $etype,
                        e.confidence  = $conf
                    WITH e
                    MATCH (p:Paper {id: $paper_id})
                    MERGE (p)-[r:HAS_ENTITY]->(e)
                    SET r.confidence = $conf
                    """,
                    id=eid,
                    text=text,
                    etype=etype,
                    conf=ent.get("confidence", 0.85),
                    paper_id=paper_id,
                )
                counts["entities"] += 1

            # Claims — stored per-paper (not deduplicated globally)
            for i, claim in enumerate(claims[:30]):
                text = (claim.get("text") or "").strip()
                if not text:
                    continue
                cid = _short_id(f"{paper_id}:claim:{i}:{text}")
                s.run(
                    """
                    MERGE (c:Claim {id: $id})
                    SET c.text             = $text,
                        c.claim_type       = $ctype,
                        c.evidence_strength = $strength,
                        c.confidence       = $conf
                    WITH c
                    MATCH (p:Paper {id: $paper_id})
                    MERGE (p)-[:MAKES_CLAIM]->(c)
                    """,
                    id=cid,
                    text=text[:500],
                    ctype=(claim.get("claim_type") or "descriptive").lower(),
                    strength=(claim.get("evidence_strength") or "moderate").lower(),
                    conf=claim.get("confidence", 0.8),
                    paper_id=paper_id,
                )
                counts["claims"] += 1

            # Mechanisms
            for i, mech in enumerate(mechanisms[:20]):
                desc = (mech.get("description") or "").strip()
                if not desc:
                    continue
                mid = _short_id(f"{paper_id}:mech:{i}:{desc}")
                s.run(
                    """
                    MERGE (m:Mechanism {id: $id})
                    SET m.description      = $desc,
                        m.upstream_entity  = $upstream,
                        m.downstream_entity = $downstream,
                        m.interaction_type = $interaction,
                        m.confidence       = $conf
                    WITH m
                    MATCH (p:Paper {id: $paper_id})
                    MERGE (p)-[:DESCRIBES_MECHANISM]->(m)
                    """,
                    id=mid,
                    desc=desc[:500],
                    upstream=(mech.get("upstream_entity") or mech.get("upstream")),
                    downstream=(mech.get("downstream_entity") or mech.get("downstream")),
                    interaction=(mech.get("interaction_type") or mech.get("interaction")),
                    conf=mech.get("confidence", 0.75),
                    paper_id=paper_id,
                )
                counts["mechanisms"] += 1

            # Methods — deduplicate by normalized name
            for method in methods[:20]:
                name = (method.get("name") or "").strip()
                if not name:
                    continue
                method_id = _short_id(f"method:{name.lower()}")
                s.run(
                    """
                    MERGE (m:Method {id: $id})
                    SET m.name     = $name,
                        m.category = $category
                    WITH m
                    MATCH (p:Paper {id: $paper_id})
                    MERGE (p)-[:USES_METHOD]->(m)
                    """,
                    id=method_id,
                    name=name,
                    category=(method.get("category") or "other").lower(),
                    paper_id=paper_id,
                )
                counts["methods"] += 1

        return counts

    # ------------------------------------------------------------------
    # Citation edges
    # ------------------------------------------------------------------

    def add_citations(self, paper_id: str, references: list[dict]) -> int:
        """Add CITES edges where referenced papers exist in the graph."""
        added = 0
        with self._driver.session() as s:
            for ref in references:
                ref_doi = (ref.get("doi") or "").strip()
                ref_title = (ref.get("title") or "").strip()

                if ref_doi:
                    result = s.run(
                        """
                        MATCH (source:Paper {id: $source_id})
                        MATCH (target:Paper {doi: $doi})
                        WHERE source.id <> target.id
                        MERGE (source)-[r:CITES]->(target)
                        RETURN count(r) as c
                        """,
                        source_id=paper_id,
                        doi=ref_doi,
                    )
                    added += result.single()["c"]
                elif ref_title:
                    # fuzzy match by title prefix (first 60 chars)
                    result = s.run(
                        """
                        MATCH (source:Paper {id: $source_id})
                        MATCH (target:Paper)
                        WHERE source.id <> target.id
                          AND toLower(target.title) STARTS WITH toLower($title_prefix)
                        MERGE (source)-[r:CITES]->(target)
                        RETURN count(r) as c
                        """,
                        source_id=paper_id,
                        title_prefix=ref_title[:60],
                    )
                    added += result.single()["c"]

        return added

    # ------------------------------------------------------------------
    # Connection edges (from discovered_connections table)
    # ------------------------------------------------------------------

    def add_connection(
        self,
        paper_a_id: str,
        paper_b_id: str,
        connection_type: str,
        description: str,
        confidence: float,
        connection_db_id: str,
    ) -> None:
        """Add a CONNECTS edge between two Paper nodes."""
        with self._driver.session() as s:
            s.run(
                """
                MATCH (a:Paper {id: $a_id})
                MATCH (b:Paper {id: $b_id})
                MERGE (a)-[r:CONNECTS {connection_id: $conn_id}]->(b)
                SET r.connection_type = $conn_type,
                    r.description     = $desc,
                    r.confidence      = $conf
                """,
                a_id=paper_a_id,
                b_id=paper_b_id,
                conn_id=connection_db_id,
                conn_type=connection_type,
                desc=description[:300],
                conf=confidence,
            )

    # ------------------------------------------------------------------
    # Stats / verification queries
    # ------------------------------------------------------------------

    def count_nodes(self) -> dict[str, int]:
        """Return count of each node label."""
        labels = ["Paper", "Researcher", "Entity", "Claim", "Mechanism", "Method"]
        counts = {}
        with self._driver.session() as s:
            for label in labels:
                result = s.run(f"MATCH (n:{label}) RETURN count(n) as c")
                counts[label] = result.single()["c"]
        return counts

    def count_edges(self) -> dict[str, int]:
        """Return count of each relationship type."""
        rel_types = [
            "AUTHORED_BY", "HAS_ENTITY", "MAKES_CLAIM",
            "DESCRIBES_MECHANISM", "USES_METHOD", "CITES", "CONNECTS",
        ]
        counts = {}
        with self._driver.session() as s:
            for rel in rel_types:
                result = s.run(f"MATCH ()-[r:{rel}]->() RETURN count(r) as c")
                counts[rel] = result.single()["c"]
        return counts

    def find_shared_entities(
        self,
        paper_id: str,
        top_k: int = 20,
    ) -> list[dict]:
        """Find papers sharing entities with the given paper."""
        with self._driver.session() as s:
            result = s.run(
                """
                MATCH (source:Paper {id: $paper_id})-[:HAS_ENTITY]->(e:Entity)
                      <-[:HAS_ENTITY]-(other:Paper)
                WHERE other.id <> $paper_id
                WITH other, collect(e.text) as shared, count(e) as cnt
                ORDER BY cnt DESC
                LIMIT $k
                RETURN other.id as paper_id, other.title as title,
                       shared, cnt as shared_count
                """,
                paper_id=paper_id,
                k=top_k,
            )
            return [dict(r) for r in result]

    def find_path(
        self,
        concept_a: str,
        concept_b: str,
        max_hops: int = 4,
    ) -> list[dict]:
        """Find shortest paths between two concepts/papers in the graph."""
        with self._driver.session() as s:
            result = s.run(
                """
                MATCH path = shortestPath(
                    (a)-[*1..$hops]-(b)
                )
                WHERE (a:Paper OR a:Entity OR a:Concept)
                  AND (b:Paper OR b:Entity OR b:Concept)
                  AND (a.title CONTAINS $ca OR a.text CONTAINS $ca OR a.name CONTAINS $ca)
                  AND (b.title CONTAINS $cb OR b.text CONTAINS $cb OR b.name CONTAINS $cb)
                RETURN [n in nodes(path) | {
                    labels: labels(n),
                    id: n.id,
                    title: n.title,
                    text: n.text,
                    name: n.name
                }] as nodes,
                [r in relationships(path) | type(r)] as rel_types,
                length(path) as hops
                ORDER BY hops
                LIMIT 5
                """,
                ca=concept_a,
                cb=concept_b,
                hops=max_hops,
            )
            return [dict(r) for r in result]
