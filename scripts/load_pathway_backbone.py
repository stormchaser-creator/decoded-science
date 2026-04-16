"""Load the Tier 1 pathway backbone into kb_pathways, kb_pathway_graph_nodes,
kb_pathway_graph_edges, and canonical_entities.

This anchors Tier 2 entity normalization — when the normalizer sees an entity
string like 'hydrocortisone' in a paper, it resolves to the canonical_entity
for 'Cortisol' which is linked to the steroidogenesis pathway node, which
carries the primary_operation=Synthesis tag that the edge synthesizer uses
to determine operation_crossing.

Idempotent: upserts on (id, pathway_id) for graph tables, on canonical_name
for canonical_entities.

Usage:
    python scripts/load_pathway_backbone.py --dry-run
    python scripts/load_pathway_backbone.py
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from collections import Counter

import psycopg2
import psycopg2.extras

from pathway_backbone_data import ALL_PATHWAYS

logging.basicConfig(level=logging.INFO,
                    format="%(asctime)s [%(levelname)s] %(message)s",
                    datefmt="%Y-%m-%d %H:%M:%S")
log = logging.getLogger("load_backbone")


# Map node_type → canonical_entities.entity_type (constrained by check)
# Allowed: gene, protein, metabolite, pathway, disease, drug, process,
#          tissue, cell_type, receptor
ENTITY_TYPE_MAP = {
    "gene": "gene",
    "protein": "protein",
    "metabolite": "metabolite",
    "receptor": "receptor",
    "complex": "protein",      # protein complex
    "process": "process",
    "drug": "drug",
    "disease": "disease",
    "tissue": "tissue",
    "cell_type": "cell_type",
    "pathway": "pathway",
}

DB_HOST = os.environ.get("PGHOST", "Whits-Mac-mini.local")
DB_NAME = os.environ.get("PGDATABASE", "encoded_human")


def db_connect():
    return psycopg2.connect(
        host=DB_HOST, dbname=DB_NAME,
        cursor_factory=psycopg2.extras.RealDictCursor,
    )


def load(dry_run: bool) -> None:
    conn = db_connect()
    stats: Counter = Counter()

    try:
        with conn.cursor() as cur:
            for pw in ALL_PATHWAYS:
                # --- Upsert pathway parent row ---
                pw_data = {
                    "description": pw["description"],
                    "nodes": len(pw["nodes"]),
                    "edges": len(pw["edges"]),
                }
                cur.execute(
                    """
                    INSERT INTO kb_pathways (id, canonical_name, category, data, operations, kegg_ids)
                    VALUES (%s, %s, %s, %s::jsonb, %s, %s)
                    ON CONFLICT (id) DO UPDATE SET
                        canonical_name = EXCLUDED.canonical_name,
                        category = EXCLUDED.category,
                        data = EXCLUDED.data,
                        operations = EXCLUDED.operations,
                        kegg_ids = EXCLUDED.kegg_ids,
                        updated_at = NOW()
                    """,
                    (
                        pw["id"], pw["canonical_name"], pw["category"],
                        json.dumps(pw_data),
                        pw["operations"],
                        pw.get("kegg_ids", []),
                    ),
                )
                stats["pathways_upserted"] += 1

                # --- Upsert nodes ---
                for node in pw["nodes"]:
                    cur.execute(
                        """
                        INSERT INTO kb_pathway_graph_nodes (
                            id, pathway_id, name, aliases, node_type, operation, description
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id, pathway_id) DO UPDATE SET
                            name = EXCLUDED.name,
                            aliases = EXCLUDED.aliases,
                            node_type = EXCLUDED.node_type,
                            operation = EXCLUDED.operation,
                            description = EXCLUDED.description
                        """,
                        (
                            node["id"], pw["id"], node["name"],
                            node.get("aliases", []),
                            node["node_type"],
                            node["operation"],
                            node.get("description"),
                        ),
                    )
                    stats["nodes_upserted"] += 1

                    # --- Also upsert into canonical_entities so Tier 2 has
                    # a lookup target for string resolution ---
                    entity_type = ENTITY_TYPE_MAP.get(node["node_type"], "process")
                    cur.execute(
                        """
                        INSERT INTO canonical_entities (
                            canonical_name, entity_type, aliases, primary_operation
                        ) VALUES (%s, %s, %s, %s)
                        ON CONFLICT (canonical_name) DO UPDATE SET
                            entity_type = EXCLUDED.entity_type,
                            aliases = EXCLUDED.aliases,
                            primary_operation = EXCLUDED.primary_operation,
                            updated_at = NOW()
                        """,
                        (
                            node["name"], entity_type,
                            node.get("aliases", []),
                            node["operation"],
                        ),
                    )
                    stats["canonical_entities_upserted"] += 1

                # --- Upsert edges ---
                for i, edge in enumerate(pw["edges"]):
                    edge_id = f"{pw['id']}_edge_{i:03d}"
                    enzyme_id = edge.get("enzyme")
                    cofactors = edge.get("cofactors", [])
                    inhibitors = edge.get("inhibitors", [])
                    cur.execute(
                        """
                        INSERT INTO kb_pathway_graph_edges (
                            id, pathway_id, from_node, to_node, edge_type,
                            mechanism, rate_limiting, reversible,
                            cofactors, enzyme, inhibitors
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        ON CONFLICT (id, pathway_id) DO UPDATE SET
                            from_node = EXCLUDED.from_node,
                            to_node = EXCLUDED.to_node,
                            edge_type = EXCLUDED.edge_type,
                            mechanism = EXCLUDED.mechanism,
                            rate_limiting = EXCLUDED.rate_limiting,
                            reversible = EXCLUDED.reversible,
                            cofactors = EXCLUDED.cofactors,
                            enzyme = EXCLUDED.enzyme,
                            inhibitors = EXCLUDED.inhibitors
                        """,
                        (
                            edge_id, pw["id"], edge["from"], edge["to"],
                            edge["edge_type"],
                            edge.get("mechanism"),
                            edge.get("rate_limiting", False),
                            edge.get("reversible", False),
                            cofactors, enzyme_id, inhibitors,
                        ),
                    )
                    stats["edges_upserted"] += 1

            if dry_run:
                conn.rollback()
                log.info("DRY RUN — rolled back")
            else:
                conn.commit()

        # Verify counts
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS n FROM kb_pathways")
            pw_n = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM kb_pathway_graph_nodes")
            nd_n = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM kb_pathway_graph_edges")
            ed_n = cur.fetchone()["n"]
            cur.execute("SELECT COUNT(*) AS n FROM canonical_entities")
            ce_n = cur.fetchone()["n"]
            cur.execute(
                """SELECT operation, COUNT(*) AS n
                   FROM kb_pathway_graph_nodes GROUP BY operation ORDER BY n DESC"""
            )
            op_dist = cur.fetchall()

        log.info("=" * 60)
        log.info("BACKBONE LOAD SUMMARY%s", " (DRY RUN)" if dry_run else "")
        log.info("=" * 60)
        for k, v in stats.most_common():
            log.info("  %-30s %s", k, v)
        log.info("")
        log.info("FINAL TABLE COUNTS:")
        log.info("  kb_pathways              %s", pw_n)
        log.info("  kb_pathway_graph_nodes   %s", nd_n)
        log.info("  kb_pathway_graph_edges   %s", ed_n)
        log.info("  canonical_entities       %s", ce_n)
        log.info("")
        log.info("OPERATION DISTRIBUTION ACROSS NODES:")
        for row in op_dist:
            log.info("  %-15s %s", row["operation"], row["n"])
    finally:
        conn.close()


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    load(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
