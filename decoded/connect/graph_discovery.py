"""Phase 1: Graph-based connection discovery.

Finds candidate paper pairs via shared Neo4j nodes:
- Shared entities (genes, proteins, diseases, drugs)
- Convergent claims (same claim type / entity overlap)
- Shared mechanisms (upstream/downstream/interaction)
- Methodological parallels (same methods used)
"""

from __future__ import annotations

import logging
from typing import Any

from neo4j import GraphDatabase

from decoded.graph.builder import NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

logger = logging.getLogger(__name__)


class GraphDiscovery:
    """Find candidate paper pairs from shared graph nodes."""

    def __init__(
        self,
        uri: str = NEO4J_URI,
        user: str = NEO4J_USER,
        password: str = NEO4J_PASSWORD,
    ):
        self._driver = GraphDatabase.driver(uri, auth=(user, password))

    def close(self) -> None:
        self._driver.close()

    # ------------------------------------------------------------------
    # Shared entities
    # ------------------------------------------------------------------

    def find_shared_entities(
        self,
        min_shared: int = 2,
        limit: int = 500,
    ) -> list[dict[str, Any]]:
        """Papers sharing ≥ min_shared Entity nodes."""
        with self._driver.session() as s:
            result = s.run(
                """
                MATCH (a:Paper)-[:HAS_ENTITY]->(e:Entity)<-[:HAS_ENTITY]-(b:Paper)
                WHERE a.id < b.id
                WITH a, b, collect(e.text) as shared_entities, count(e) as shared_count
                WHERE shared_count >= $min_shared
                RETURN a.id as paper_a_id, b.id as paper_b_id,
                       shared_entities, shared_count,
                       'shared_entities' as discovery_method
                ORDER BY shared_count DESC
                LIMIT $limit
                """,
                min_shared=min_shared,
                limit=limit,
            )
            return [dict(r) for r in result]

    # ------------------------------------------------------------------
    # Convergent claims
    # ------------------------------------------------------------------

    def find_convergent_claims(self, limit: int = 300) -> list[dict[str, Any]]:
        """Papers with claims of the same type involving overlapping entities."""
        with self._driver.session() as s:
            result = s.run(
                """
                MATCH (a:Paper)-[:MAKES_CLAIM]->(ca:Claim)
                MATCH (b:Paper)-[:MAKES_CLAIM]->(cb:Claim)
                WHERE a.id < b.id
                  AND ca.claim_type = cb.claim_type
                  AND ca.claim_type <> 'descriptive'
                WITH a, b,
                     collect(DISTINCT ca.claim_type)[0] as claim_type,
                     count(DISTINCT ca) + count(DISTINCT cb) as total_claims,
                     'convergent_claims' as discovery_method
                RETURN a.id as paper_a_id, b.id as paper_b_id,
                       [] as shared_entities,
                       total_claims as shared_count,
                       discovery_method,
                       claim_type
                ORDER BY total_claims DESC
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(r) for r in result]

    # ------------------------------------------------------------------
    # Shared mechanisms
    # ------------------------------------------------------------------

    def find_shared_mechanisms(self, limit: int = 300) -> list[dict[str, Any]]:
        """Papers describing mechanisms with overlapping upstream/downstream entities."""
        with self._driver.session() as s:
            result = s.run(
                """
                MATCH (a:Paper)-[:DESCRIBES_MECHANISM]->(ma:Mechanism)
                MATCH (b:Paper)-[:DESCRIBES_MECHANISM]->(mb:Mechanism)
                WHERE a.id < b.id
                  AND ma.id <> mb.id
                  AND (
                    (ma.upstream_entity IS NOT NULL AND mb.upstream_entity IS NOT NULL
                     AND toLower(ma.upstream_entity) = toLower(mb.upstream_entity))
                    OR
                    (ma.downstream_entity IS NOT NULL AND mb.downstream_entity IS NOT NULL
                     AND toLower(ma.downstream_entity) = toLower(mb.downstream_entity))
                    OR
                    (ma.interaction_type IS NOT NULL AND mb.interaction_type IS NOT NULL
                     AND toLower(ma.interaction_type) = toLower(mb.interaction_type))
                  )
                WITH a, b,
                     collect(DISTINCT coalesce(ma.upstream_entity, ma.downstream_entity)) as shared_entities,
                     count(*) as shared_count
                RETURN a.id as paper_a_id, b.id as paper_b_id,
                       shared_entities, shared_count,
                       'shared_mechanisms' as discovery_method
                ORDER BY shared_count DESC
                LIMIT $limit
                """,
                limit=limit,
            )
            return [dict(r) for r in result]

    # ------------------------------------------------------------------
    # Methodological parallels
    # ------------------------------------------------------------------

    def find_methodological_parallels(
        self,
        min_shared: int = 2,
        limit: int = 200,
    ) -> list[dict[str, Any]]:
        """Papers using the same experimental/analytical methods."""
        with self._driver.session() as s:
            result = s.run(
                """
                MATCH (a:Paper)-[:USES_METHOD]->(m:Method)<-[:USES_METHOD]-(b:Paper)
                WHERE a.id < b.id
                WITH a, b, collect(m.name) as shared_methods, count(m) as shared_count
                WHERE shared_count >= $min_shared
                RETURN a.id as paper_a_id, b.id as paper_b_id,
                       shared_methods as shared_entities,
                       shared_count,
                       'methodological_parallels' as discovery_method
                ORDER BY shared_count DESC
                LIMIT $limit
                """,
                min_shared=min_shared,
                limit=limit,
            )
            return [dict(r) for r in result]

    # ------------------------------------------------------------------
    # Combined candidate set
    # ------------------------------------------------------------------

    def get_all_candidates(self) -> list[dict[str, Any]]:
        """Gather all candidate pairs from all discovery methods."""
        candidates = {}

        for find_fn in [
            self.find_shared_entities,
            self.find_convergent_claims,
            self.find_shared_mechanisms,
            self.find_methodological_parallels,
        ]:
            try:
                results = find_fn()
                for r in results:
                    key = (r["paper_a_id"], r["paper_b_id"])
                    if key not in candidates:
                        candidates[key] = r
                    else:
                        # Merge: keep highest shared_count, accumulate methods
                        existing = candidates[key]
                        if r.get("shared_count", 0) > existing.get("shared_count", 0):
                            candidates[key] = r
                        # Append discovery method
                        if r.get("discovery_method") not in existing.get("discovery_method", ""):
                            existing["discovery_method"] = (
                                existing.get("discovery_method", "")
                                + "," + r.get("discovery_method", "")
                            )
            except Exception as exc:
                logger.warning("Graph discovery error in %s: %s", find_fn.__name__, exc)

        logger.info("Graph discovery found %d unique candidate pairs", len(candidates))
        return list(candidates.values())

    # ------------------------------------------------------------------
    # Bridge path query
    # ------------------------------------------------------------------

    def find_bridge_path(
        self,
        concept_a: str,
        concept_b: str,
        max_hops: int = 4,
    ) -> list[dict[str, Any]]:
        """Find paths between two concepts in the graph (for bridge queries)."""
        with self._driver.session() as s:
            result = s.run(
                """
                MATCH path = shortestPath(
                    (a)-[*1..$hops]-(b)
                )
                WHERE (a.title CONTAINS $ca OR a.text CONTAINS $ca OR a.name CONTAINS $ca)
                  AND (b.title CONTAINS $cb OR b.text CONTAINS $cb OR b.name CONTAINS $cb)
                  AND a.id <> b.id
                RETURN [n in nodes(path) | {
                    labels: labels(n),
                    id: coalesce(n.id, ''),
                    title: coalesce(n.title, ''),
                    text: coalesce(n.text, ''),
                    name: coalesce(n.name, '')
                }] as path_nodes,
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
