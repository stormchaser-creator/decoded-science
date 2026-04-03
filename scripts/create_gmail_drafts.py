"""Standalone script: create Gmail drafts for all 'drafted' outreach items.

Use this to backfill items that were drafted before GMAIL_APP_PASSWORD was
configured, or to retry failed Gmail draft creation attempts.

Usage:
    cd ~/Projects/Decoded && source .venv/bin/activate
    python scripts/create_gmail_drafts.py              # process all 'drafted' items
    python scripts/create_gmail_drafts.py --limit 5    # process up to 5
    python scripts/create_gmail_drafts.py --dry-run    # print but don't create

Prerequisites:
    GMAIL_FROM_EMAIL=Drericwhitney@gmail.com in .env
    GMAIL_APP_PASSWORD=<16-char app password> in .env

Generate an app password at: https://myaccount.google.com/apppasswords
(Requires 2-Step Verification to be enabled on the Gmail account)
"""

from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from dotenv import load_dotenv
load_dotenv(_ROOT / ".env", override=True)

import psycopg2
import psycopg2.extras

from decoded.outreach.gmail_drafts import GmailDraftCreator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("scripts.create_gmail_drafts")


def get_db_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    return conn


def fetch_drafted(conn, limit: int) -> list[dict]:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT id, to_name, to_email, subject, body
        FROM reach_paper_outreach
        WHERE status = 'drafted'
          AND to_email IS NOT NULL
          AND body IS NOT NULL
        ORDER BY drafted_at ASC
        LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]


def mark_gmail_created(conn, outreach_id: int) -> None:
    conn.cursor().execute(
        "UPDATE reach_paper_outreach SET status = 'gmail_draft_created' WHERE id = %s",
        (outreach_id,),
    )
    conn.commit()


def main():
    parser = argparse.ArgumentParser(description="Create Gmail drafts for outreach items")
    parser.add_argument("--limit", type=int, default=50, help="Max items to process (default: 50)")
    parser.add_argument("--dry-run", action="store_true", help="Print what would happen, don't create drafts")
    args = parser.parse_args()

    if not GmailDraftCreator.is_configured():
        print("ERROR: GMAIL_APP_PASSWORD not set in .env")
        print("Generate one at: https://myaccount.google.com/apppasswords")
        sys.exit(1)

    creator = GmailDraftCreator()
    conn = get_db_conn()
    items = fetch_drafted(conn, limit=args.limit)

    if not items:
        print("No 'drafted' items waiting for Gmail draft creation.")
        return

    print(f"Found {len(items)} drafted items. Creating Gmail drafts...")
    success = failed = 0

    for item in items:
        if args.dry_run:
            print(f"  [dry-run] Would create draft: id={item['id']} → {item['to_email']} | {item['subject']}")
            success += 1
            continue

        try:
            creator.create_draft(
                to_name=item["to_name"] or "",
                to_email=item["to_email"],
                subject=item["subject"] or "(no subject)",
                body=item["body"],
                outreach_id=item["id"],
            )
            mark_gmail_created(conn, item["id"])
            print(f"  ✓ id={item['id']} → {item['to_email']}")
            success += 1
        except Exception as exc:
            logger.error("Failed id=%d: %s", item["id"], exc)
            failed += 1

    conn.close()
    print(f"\nDone. Success: {success}  Failed: {failed}")


if __name__ == "__main__":
    main()
