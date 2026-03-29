#!/usr/bin/env python3
"""
Entity co-occurrence connection generator.
Creates connections between papers sharing 3+ entities (cross-discipline)
or 5+ entities (same discipline). Inserts into discovered_connections.

Run: python scripts/entity_cooccurrence.py
"""

import json
import os
import sys
from collections import defaultdict
import psycopg2
import psycopg2.extras

DATABASE_URL = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")

CROSS_DISCIPLINE_THRESHOLD = 3
SAME_DISCIPLINE_THRESHOLD = 3
BATCH_SIZE = 500


def normalize_entity(name):
    if not name:
        return None
    return name.lower().strip()


def main():
    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    print("Loading papers and entities from extraction_results...", flush=True)
    cur.execute("""
        SELECT er.paper_id, er.entities, p.source as discipline
        FROM extraction_results er
        JOIN raw_papers p ON p.id = er.paper_id
        WHERE er.entities IS NOT NULL
          AND er.entities != 'null'
          AND er.entities::text LIKE '[%'
    """)
    rows = cur.fetchall()
    print(f"  Loaded {len(rows)} papers with entities", flush=True)

    # Build entity → [(paper_id, discipline)] map
    entity_papers = defaultdict(list)
    paper_entities = {}

    for row in rows:
        pid = str(row["paper_id"])
        disc = row["discipline"] or "unknown"
        try:
            entities = row["entities"]
            if isinstance(entities, str):
                entities = json.loads(entities)
            if not isinstance(entities, list):
                continue
        except Exception:
            continue

        names = set()
        for e in entities:
            if isinstance(e, dict):
                name = normalize_entity(e.get("normalized_name") or e.get("name") or e.get("text"))
            elif isinstance(e, str):
                name = normalize_entity(e)
            else:
                name = None
            if name and len(name) > 2:
                names.add(name)

        if names:
            paper_entities[pid] = {"entities": names, "discipline": disc}
            for name in names:
                entity_papers[name].append(pid)

    print(f"  {len(paper_entities)} papers with usable entities", flush=True)
    print(f"  {len(entity_papers)} unique entities", flush=True)

    # Count shared entities per paper pair
    print("Computing pair overlap...", flush=True)
    pair_shared = defaultdict(set)
    for entity_name, pids in entity_papers.items():
        if len(pids) < 2 or len(pids) > 200:  # skip very common entities
            continue
        for i in range(len(pids)):
            for j in range(i + 1, len(pids)):
                a, b = min(pids[i], pids[j]), max(pids[i], pids[j])
                pair_shared[(a, b)].add(entity_name)

    print(f"  {len(pair_shared)} candidate pairs", flush=True)

    # Filter pairs by threshold
    qualified = []
    for (a, b), shared in pair_shared.items():
        disc_a = paper_entities.get(a, {}).get("discipline", "unknown")
        disc_b = paper_entities.get(b, {}).get("discipline", "unknown")
        same_disc = disc_a == disc_b
        threshold = SAME_DISCIPLINE_THRESHOLD if same_disc else CROSS_DISCIPLINE_THRESHOLD
        if len(shared) >= threshold:
            shared_list = sorted(shared)[:10]
            qualified.append({
                "paper_a": a,
                "paper_b": b,
                "shared": shared_list,
                "count": len(shared),
                "same_disc": same_disc,
            })

    print(f"  {len(qualified)} pairs qualify (≥{CROSS_DISCIPLINE_THRESHOLD} cross-disc, ≥{SAME_DISCIPLINE_THRESHOLD} same-disc)", flush=True)

    # Check which already exist
    print("Checking for existing connections...", flush=True)
    cur.execute("""
        SELECT paper_a_id::text, paper_b_id::text
        FROM discovered_connections
        WHERE connection_type = 'entity_cooccurrence'
    """)
    existing = {(str(r["paper_a_id"]), str(r["paper_b_id"])) for r in cur.fetchall()}
    existing |= {(b, a) for a, b in existing}

    new_pairs = [p for p in qualified if (p["paper_a"], p["paper_b"]) not in existing]
    print(f"  {len(existing)//2} already exist, {len(new_pairs)} new to insert", flush=True)

    if not new_pairs:
        print("Nothing to insert. Done.")
        conn.close()
        return

    # Insert in batches
    inserted = 0
    for i in range(0, len(new_pairs), BATCH_SIZE):
        batch = new_pairs[i:i + BATCH_SIZE]
        args = []
        for p in batch:
            shared_str = ", ".join(p["shared"][:5])
            description = f"Papers share {p['count']} entities: {shared_str}"
            novelty = 0.15 if p["same_disc"] else 0.30
            strength = min(p["count"] / 10.0, 1.0)
            args.append((
                p["paper_a"], p["paper_b"],
                "entity_cooccurrence",
                description, strength, novelty,
                # no extra fields needed — model_id handled in template
            ))

        psycopg2.extras.execute_values(cur, """
            INSERT INTO discovered_connections
                (paper_a_id, paper_b_id, connection_type, description, confidence, novelty_score, model_id)
            VALUES %s
            ON CONFLICT DO NOTHING
        """, args, template="(%s::uuid, %s::uuid, %s, %s, %s, %s, 'graph_query')")
        conn.commit()
        inserted += len(batch)
        print(f"  Inserted {inserted}/{len(new_pairs)}...", end="\r", flush=True)

    print(f"\nDone. Inserted {len(new_pairs)} entity co-occurrence connections.")
    conn.close()


if __name__ == "__main__":
    main()
