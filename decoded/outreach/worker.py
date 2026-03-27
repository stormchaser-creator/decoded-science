"""Author outreach worker.

CLI usage:
    python -m decoded.outreach.worker --generate 3     # generate 3 sample emails
    python -m decoded.outreach.worker --generate 3 --dry-run   # print, don't queue
    python -m decoded.outreach.worker --list           # show pending queue
    python -m decoded.outreach.worker --unsubscribe email@example.com
    python -m decoded.outreach.worker --stats          # queue statistics
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from pathlib import Path
from typing import Any

import psycopg2
import psycopg2.extras
from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=False)

from decoded.outreach.email_extractor import enrich_paper_contacts
from decoded.outreach.templates import EmailTemplateGenerator, generate_static_email
from decoded.outreach import queue as outreach_queue

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("decoded.outreach.worker")


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def get_db_conn():
    db_url = os.environ.get("DATABASE_URL", "postgresql://whit@localhost:5432/encoded_human")
    conn = psycopg2.connect(db_url)
    conn.autocommit = False
    psycopg2.extras.register_uuid(conn)
    return conn


def fetch_papers_with_connections(conn, limit: int) -> list[dict]:
    """Fetch papers that have connections and extraction data."""
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT DISTINCT ON (p.id)
               p.id, p.title, p.authors, p.doi, p.journal,
               p.published_date, p.source, p.pmc_id, p.raw_metadata,
               e.key_findings, e.entities,
               dc.id as connection_id,
               dc.connection_type, dc.description as connection_description,
               dc.confidence,
               CASE WHEN dc.paper_a_id = p.id THEN dc.paper_b_id ELSE dc.paper_a_id END as connected_paper_id
        FROM raw_papers p
        JOIN extraction_results e ON e.paper_id = p.id
        JOIN discovered_connections dc ON dc.paper_a_id = p.id OR dc.paper_b_id = p.id
        WHERE p.authors IS NOT NULL
          AND jsonb_array_length(p.authors) > 0
        ORDER BY p.id, dc.confidence DESC
        LIMIT %s
        """,
        (limit,),
    )
    return [dict(r) for r in cur.fetchall()]


def fetch_paper_by_id(conn, paper_id: str) -> dict | None:
    cur = conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
    cur.execute(
        """
        SELECT p.id, p.title, p.authors, p.doi, p.journal,
               p.published_date, p.source, p.pmc_id, p.raw_metadata,
               e.key_findings
        FROM raw_papers p
        LEFT JOIN extraction_results e ON e.paper_id = p.id
        WHERE p.id = %s
        """,
        (paper_id,),
    )
    row = cur.fetchone()
    return dict(row) if row else None


# ---------------------------------------------------------------------------
# OutreachWorker
# ---------------------------------------------------------------------------

class OutreachWorker:
    """Generate and queue author outreach emails."""

    def __init__(
        self,
        use_llm: bool = True,
        dry_run: bool = False,
        sender_name: str = "The Decoded Team",
        sender_email: str = "hello@decoded.ai",
    ):
        self.use_llm = use_llm
        self.dry_run = dry_run
        self.sender_name = sender_name
        self.sender_email = sender_email
        self._generator = EmailTemplateGenerator() if use_llm else None

    def generate_emails(self, limit: int = 10) -> list[dict[str, Any]]:
        """Generate outreach emails for papers with connections."""
        conn = get_db_conn()
        papers_with_connections = fetch_papers_with_connections(conn, limit=limit)

        if not papers_with_connections:
            logger.info("No papers with connections found for outreach")
            return []

        logger.info("Generating emails for %d papers...", len(papers_with_connections))

        # Enrich with contact info
        enriched = enrich_paper_contacts(papers_with_connections)
        emails = []

        for paper in enriched:
            connected_paper_id = paper.get("connected_paper_id")
            connected_paper = fetch_paper_by_id(conn, str(connected_paper_id)) if connected_paper_id else {}

            connection = {
                "id": paper.get("connection_id", ""),
                "connection_type": paper.get("connection_type", "convergent_evidence"),
                "description": paper.get("connection_description", ""),
                "confidence": float(paper.get("confidence", 0.5)),
            }

            try:
                if self.use_llm and self._generator:
                    email = self._generator.generate(
                        paper=paper,
                        connection=connection,
                        connected_paper=connected_paper or {},
                        sender_name=self.sender_name,
                        sender_email=self.sender_email,
                    )
                else:
                    email = generate_static_email(
                        paper=paper,
                        connection=connection,
                        connected_paper=connected_paper or {},
                        sender_name=self.sender_name,
                    )

                emails.append(email)

                if not self.dry_run:
                    qid = outreach_queue.enqueue(email)
                    if qid > 0:
                        logger.info("Queued email %d for %s", qid, email.get("to_name", "?"))

            except Exception as exc:
                logger.error("Email generation failed: %s", exc, exc_info=True)

        conn.close()
        return emails

    def print_emails(self, emails: list[dict]) -> None:
        """Pretty-print generated emails for review."""
        print(f"\n{'='*70}")
        print(f"Generated {len(emails)} outreach email(s)")
        print(f"{'='*70}")
        for i, email in enumerate(emails, 1):
            print(f"\n--- Email {i}/{len(emails)} ---")
            print(f"To:       {email.get('to_name', 'Unknown')} <{email.get('to_email', 'no email')}>")
            print(f"Subject:  {email.get('subject', '')}")
            print(f"Cost:     ${email.get('cost_usd', 0):.4f}")
            print(f"\n{email.get('body', '')}")
            print(f"{'─'*60}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        description="Decoded author outreach worker"
    )
    parser.add_argument("--generate", type=int, metavar="N",
                        help="Generate N outreach emails")
    parser.add_argument("--dry-run", action="store_true",
                        help="Generate but don't queue (print to stdout)")
    parser.add_argument("--no-llm", action="store_true",
                        help="Use static templates instead of LLM")
    parser.add_argument("--list", action="store_true",
                        help="List pending queue")
    parser.add_argument("--stats", action="store_true",
                        help="Show queue statistics")
    parser.add_argument("--unsubscribe", metavar="EMAIL",
                        help="Add email to unsubscribe list")
    args = parser.parse_args()

    if args.unsubscribe:
        outreach_queue.unsubscribe(args.unsubscribe)
        print(f"Unsubscribed: {args.unsubscribe}")
        return

    if args.stats:
        stats = outreach_queue.queue_stats()
        print("\n=== Outreach Queue Stats ===")
        for k, v in stats.items():
            print(f"  {k}: {v}")
        return

    if args.list:
        pending = outreach_queue.get_pending(limit=20)
        print(f"\n=== Pending Queue ({len(pending)} emails) ===")
        for item in pending:
            print(f"  [{item['id']}] {item['to_name']} <{item['to_email']}> | {item['subject'][:50]}")
        return

    if args.generate:
        worker = OutreachWorker(
            use_llm=not args.no_llm,
            dry_run=args.dry_run,
        )
        emails = worker.generate_emails(limit=args.generate)
        worker.print_emails(emails)

        if not args.dry_run:
            stats = outreach_queue.queue_stats()
            print(f"\nQueue status: {stats}")
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
