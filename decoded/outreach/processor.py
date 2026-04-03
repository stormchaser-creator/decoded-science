"""Decoded outreach processor.

Processes pending_draft items from the reach_paper_outreach table:
  1. Fetches paper details from Decoded's raw_papers / extraction_results
  2. Extracts corresponding author contact (email)
  3. Generates the 5-part email via PaperOutreachGenerator (AutoAIBiz reach agent)
  4. Updates reach_paper_outreach with subject, body, to_email → status=drafted

The reach_paper_outreach table lives in the shared encoded_human PostgreSQL DB.
Decoded's connect worker inserts rows (status=pending_draft) after storing
high-confidence connections; this processor enriches them.

CLI:
    python -m decoded.outreach.processor           # process up to 10 pending items
    python -m decoded.outreach.processor --limit 5 # process up to 5
    python -m decoded.outreach.processor --dry-run # generate but don't save
    python -m decoded.outreach.processor --stats   # show queue stats
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=True)

# Add AutoAIBiz to path so we can import the reach paper outreach generator
_AUTOAIBIZ_PATH = Path.home() / "Projects" / "AutoAIBiz"
if str(_AUTOAIBIZ_PATH) not in sys.path:
    sys.path.insert(0, str(_AUTOAIBIZ_PATH))

from decoded.outreach.email_extractor import enrich_paper_contacts
from decoded.outreach.gmail_drafts import GmailDraftCreator

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("decoded.outreach.processor")

# 90-day author cooldown (in seconds)
COOLDOWN_SECS = 90 * 86400


def get_db_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    psycopg2.extras.register_uuid(conn)
    return conn


# ---------------------------------------------------------------------------
# Queue helpers (reach_paper_outreach table)
# ---------------------------------------------------------------------------

def fetch_pending(conn, limit: int = 10) -> list[dict]:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT id, connection_id::text, paper_a_id::text, paper_b_id::text,
               connection_type, confidence
        FROM reach_paper_outreach
        WHERE status = 'pending_draft'
        ORDER BY created_at ASC
        LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]


def mark_drafted(
    conn,
    outreach_id: int,
    to_name: str,
    to_email: str,
    subject: str,
    body: str,
    cost_usd: float,
) -> None:
    conn.cursor().execute(
        """
        UPDATE reach_paper_outreach
        SET status = 'drafted',
            to_name = %s, to_email = %s,
            subject = %s, body = %s,
            llm_cost_usd = llm_cost_usd + %s,
            drafted_at = NOW()
        WHERE id = %s
        """,
        (to_name, to_email, subject, body, cost_usd, outreach_id),
    )
    conn.commit()


def mark_gmail_draft_created(conn, outreach_id: int) -> None:
    conn.cursor().execute(
        """
        UPDATE reach_paper_outreach
        SET status = 'gmail_draft_created'
        WHERE id = %s
        """,
        (outreach_id,),
    )
    conn.commit()


def mark_skipped(conn, outreach_id: int, reason: str = "") -> None:
    conn.cursor().execute(
        "UPDATE reach_paper_outreach SET status = 'skipped', error = %s WHERE id = %s",
        (reason, outreach_id),
    )
    conn.commit()


def mark_failed(conn, outreach_id: int, error: str) -> None:
    conn.cursor().execute(
        "UPDATE reach_paper_outreach SET status = 'failed', error = %s WHERE id = %s",
        (error, outreach_id),
    )
    conn.commit()


def fetch_queue_stats(conn) -> dict:
    cur = conn.cursor()
    stats = {}
    for status in ("pending_draft", "drafted", "gmail_draft_created", "sent", "skipped", "failed"):
        cur.execute(
            "SELECT count(*) FROM reach_paper_outreach WHERE status = %s",
            (status,),
        )
        stats[status] = cur.fetchone()[0]
    cur.execute("SELECT count(*) FROM reach_paper_outreach")
    stats["total"] = cur.fetchone()[0]
    return stats


def is_in_cooldown(conn, email: str) -> bool:
    """True if we've sent to this email within 90 days."""
    if not email:
        return False
    cur = conn.cursor()
    cur.execute(
        """
        SELECT 1 FROM reach_paper_outreach
        WHERE to_email = %s AND status IN ('sent', 'gmail_draft_created')
          AND sent_at > NOW() - INTERVAL '90 days'
        LIMIT 1
        """,
        (email.lower().strip(),),
    )
    return cur.fetchone() is not None


def is_unsubscribed(conn, email: str) -> bool:
    cur = conn.cursor()
    cur.execute(
        "SELECT 1 FROM reach_paper_outreach_unsubscribes WHERE email = %s",
        (email.lower().strip(),),
    )
    return cur.fetchone() is not None


# ---------------------------------------------------------------------------
# Paper details fetch
# ---------------------------------------------------------------------------

def fetch_paper(conn, paper_id: str) -> dict | None:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT p.id, p.title, p.authors, p.doi, p.journal,
               p.published_date, p.source, p.pmc_id, p.raw_metadata,
               e.key_findings, e.entities
        FROM raw_papers p
        LEFT JOIN extraction_results e ON e.paper_id = p.id
        WHERE p.id = %s
        """,
        (paper_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


def fetch_connection(conn, connection_id: str) -> dict | None:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT id::text, paper_a_id::text, paper_b_id::text,
               connection_type, description, confidence
        FROM discovered_connections
        WHERE id = %s
        """,
        (connection_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# Processor
# ---------------------------------------------------------------------------

class OutreachProcessor:
    """Process pending_draft items from reach_paper_outreach into drafted emails."""

    def __init__(self, dry_run: bool = False) -> None:
        self.dry_run = dry_run
        self._generator = self._load_generator()
        self._gmail = self._load_gmail_creator()

    def _load_generator(self):
        try:
            from agents.reach.src.paper_outreach_generator import PaperOutreachGenerator
            return PaperOutreachGenerator()
        except ImportError as exc:
            logger.error(
                "Cannot import PaperOutreachGenerator from AutoAIBiz: %s. "
                "Ensure AutoAIBiz is at ~/Projects/AutoAIBiz.",
                exc,
            )
            raise

    def _load_gmail_creator(self) -> GmailDraftCreator | None:
        if not GmailDraftCreator.is_configured():
            logger.info(
                "GMAIL_APP_PASSWORD not set — Gmail draft creation disabled. "
                "Set it in .env to enable autonomous draft creation."
            )
            return None
        try:
            creator = GmailDraftCreator()
            logger.info("Gmail draft creation enabled (from=%s)", creator.from_email)
            return creator
        except Exception as exc:
            logger.warning("Gmail draft creator unavailable: %s", exc)
            return None

    def process_pending(self, limit: int = 10) -> dict[str, int]:
        stats = {"processed": 0, "drafted": 0, "skipped": 0, "failed": 0}
        conn = get_db_conn()

        pending = fetch_pending(conn, limit=limit)
        if not pending:
            logger.info("No pending_draft items in reach_paper_outreach")
            return stats

        logger.info("Processing %d pending outreach items...", len(pending))

        for item in pending:
            stats["processed"] += 1
            try:
                result = self._process_one(conn, item)
                if result == "drafted":
                    stats["drafted"] += 1
                elif result == "skipped":
                    stats["skipped"] += 1
                else:
                    stats["failed"] += 1
            except Exception as exc:
                logger.error("Error processing outreach item %s: %s", item["id"], exc, exc_info=True)
                if not self.dry_run:
                    mark_failed(conn, item["id"], str(exc))
                stats["failed"] += 1

        conn.close()
        return stats

    def _process_one(self, conn, item: dict) -> str:
        outreach_id = item["id"]
        logger.info("Processing outreach item %d (connection %s...)", outreach_id, item["connection_id"][:8])

        # Fetch paper details
        paper_a = fetch_paper(conn, item["paper_a_id"])
        paper_b = fetch_paper(conn, item["paper_b_id"])

        if not paper_a or not paper_a.get("title"):
            reason = f"paper_a {item['paper_a_id']} not found or has no title"
            logger.warning("Skipping item %d: %s", outreach_id, reason)
            if not self.dry_run:
                mark_skipped(conn, outreach_id, reason)
            return "skipped"

        if not paper_b or not paper_b.get("title"):
            reason = f"paper_b {item['paper_b_id']} not found or has no title"
            logger.warning("Skipping item %d: %s", outreach_id, reason)
            if not self.dry_run:
                mark_skipped(conn, outreach_id, reason)
            return "skipped"

        # Enrich with contact info
        enriched = enrich_paper_contacts([paper_a])
        paper_a = enriched[0] if enriched else paper_a
        contact = paper_a.get("contact") or {}
        author_email = contact.get("email")

        if not author_email:
            reason = "no author email found"
            logger.info("Skipping item %d: %s (paper: %s)", outreach_id, reason, paper_a.get("title", "?")[:60])
            if not self.dry_run:
                mark_skipped(conn, outreach_id, reason)
            return "skipped"

        # Cooldown / unsubscribe checks
        if is_unsubscribed(conn, author_email):
            logger.info("Skipping item %d: author %s is unsubscribed", outreach_id, author_email)
            if not self.dry_run:
                mark_skipped(conn, outreach_id, "unsubscribed")
            return "skipped"

        if is_in_cooldown(conn, author_email):
            logger.info("Skipping item %d: author %s in 90-day cooldown", outreach_id, author_email)
            if not self.dry_run:
                mark_skipped(conn, outreach_id, "90-day cooldown")
            return "skipped"

        # Fetch connection details
        connection = fetch_connection(conn, item["connection_id"])
        if not connection:
            # Fall back to item-level fields
            connection = {
                "connection_type": item.get("connection_type", "convergent_evidence"),
                "description": "",
                "confidence": item.get("confidence", 0.7),
            }

        # Generate email
        result = self._generator.generate(
            paper_a=paper_a,
            paper_b=paper_b,
            connection=connection,
            contact=contact,
        )

        if self.dry_run:
            logger.info(
                "DRY RUN — would draft email to %s <%s>\nSubject: %s\n\n%s",
                result["to_name"],
                result["to_email"],
                result["subject"],
                result["body"][:400],
            )
            return "drafted"

        mark_drafted(
            conn,
            outreach_id=outreach_id,
            to_name=result["to_name"],
            to_email=result["to_email"],
            subject=result["subject"],
            body=result["body"],
            cost_usd=result["cost_usd"],
        )

        logger.info(
            "Drafted email %d → %s <%s> | cost $%.4f",
            outreach_id,
            result["to_name"],
            result["to_email"],
            result["cost_usd"],
        )

        # Autonomously create Gmail draft if credentials are available
        if self._gmail is not None:
            try:
                self._gmail.create_draft(
                    to_name=result["to_name"],
                    to_email=result["to_email"],
                    subject=result["subject"],
                    body=result["body"],
                    outreach_id=outreach_id,
                )
                mark_gmail_draft_created(conn, outreach_id)
                logger.info("Gmail draft created for outreach item %d", outreach_id)
            except Exception as exc:
                # Non-fatal: leave as 'drafted' so the backfill script can retry
                logger.warning(
                    "Gmail draft creation failed for item %d: %s — left as 'drafted' for retry",
                    outreach_id,
                    exc,
                )

        return "drafted"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Decoded outreach processor")
    parser.add_argument("--limit", type=int, default=10,
                        help="Max pending items to process (default: 10)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate emails but don't save to DB")
    parser.add_argument("--stats", action="store_true",
                        help="Show queue statistics")
    args = parser.parse_args()

    if args.stats:
        conn = get_db_conn()
        stats = fetch_queue_stats(conn)
        conn.close()
        print("\n=== Reach Paper Outreach Queue ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        return

    processor = OutreachProcessor(dry_run=args.dry_run)
    stats = processor.process_pending(limit=args.limit)

    print("\n=== Outreach Processing Summary ===")
    for k, v in stats.items():
        print(f"  {k}: {v}")


if __name__ == "__main__":
    main()
