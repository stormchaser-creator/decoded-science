"""Backfill reach_paper_outreach from existing discovered_connections.

All discovered_connections with confidence >= 0.7 that aren't already in
reach_paper_outreach get inserted as pending_draft rows. The outreach
processor (decoded-outreach) will then draft the actual emails.

Usage:
    cd /Users/whit/Projects/Decoded
    source .venv/bin/activate
    python scripts/backfill_outreach.py              # dry-run by default
    python scripts/backfill_outreach.py --commit     # write to DB
    python scripts/backfill_outreach.py --commit --limit 100  # first 100 only
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(_ROOT / ".env", override=False)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("backfill_outreach")

MIN_CONFIDENCE = 0.7


def get_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    psycopg2.extras.register_uuid(conn)
    return conn


def run(commit: bool, limit: int | None) -> None:
    conn = get_conn()
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    # How many are already in the queue?
    cur.execute("SELECT COUNT(*) FROM reach_paper_outreach")
    existing = cur.fetchone()["count"]
    logger.info("reach_paper_outreach currently has %d rows", existing)

    # Fetch eligible connections not yet queued
    limit_clause = f"LIMIT {limit}" if limit else ""
    cur.execute(
        f"""
        SELECT dc.id::text AS connection_id,
               dc.paper_a_id::text,
               dc.paper_b_id::text,
               dc.connection_type,
               dc.confidence
        FROM discovered_connections dc
        WHERE dc.confidence >= %s
          AND NOT EXISTS (
              SELECT 1 FROM reach_paper_outreach rpo
              WHERE rpo.connection_id = dc.id
          )
        ORDER BY dc.confidence DESC, dc.created_at ASC
        {limit_clause}
        """,
        (MIN_CONFIDENCE,),
    )
    rows = cur.fetchall()
    logger.info("Found %d connections to backfill", len(rows))

    if not rows:
        logger.info("Nothing to do.")
        conn.close()
        return

    if not commit:
        logger.info("DRY RUN — would insert %d rows. Pass --commit to write.", len(rows))
        # Show a sample
        for r in rows[:5]:
            logger.info(
                "  connection %s | %s | conf=%.3f",
                r["connection_id"][:8],
                r["connection_type"],
                r["confidence"],
            )
        if len(rows) > 5:
            logger.info("  ... and %d more", len(rows) - 5)
        conn.close()
        return

    # Bulk insert with ON CONFLICT DO NOTHING to be safe
    insert_cur = conn.cursor()
    inserted = 0
    for r in rows:
        insert_cur.execute(
            """
            INSERT INTO reach_paper_outreach
                (connection_id, paper_a_id, paper_b_id, connection_type, confidence, status, created_at)
            VALUES (%s::uuid, %s::uuid, %s::uuid, %s, %s, 'pending_draft', NOW())
            ON CONFLICT (connection_id) DO NOTHING
            """,
            (
                r["connection_id"],
                r["paper_a_id"],
                r["paper_b_id"],
                r["connection_type"],
                r["confidence"],
            ),
        )
        inserted += insert_cur.rowcount

    conn.commit()
    logger.info("Inserted %d rows into reach_paper_outreach", inserted)

    # Final stats
    insert_cur.execute(
        "SELECT status, COUNT(*) FROM reach_paper_outreach GROUP BY status ORDER BY status"
    )
    for row in insert_cur.fetchall():
        logger.info("  status=%-20s count=%d", row[0], row[1])

    conn.close()


def main():
    parser = argparse.ArgumentParser(description="Backfill outreach queue from discovered_connections")
    parser.add_argument("--commit", action="store_true",
                        help="Write to DB (default is dry-run)")
    parser.add_argument("--limit", type=int, default=None,
                        help="Max rows to insert (default: all)")
    args = parser.parse_args()
    run(commit=args.commit, limit=args.limit)


if __name__ == "__main__":
    main()
