"""Outreach queue: thoughtful one-at-a-time sending with safety rails.

Features:
- SQLite-backed queue (independent of main Postgres DB)
- Rate limiting: one email per author per 90 days
- Unsubscribe tracking
- Dry-run mode (generate but don't send)
- Manual review before send
- Connection dedup: one outreach per discovered connection
- Status flow: pending_draft → drafted → approved → sent (or skipped)
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# SQLite DB for outreach tracking (not in main Postgres)
OUTREACH_DB = Path.home() / ".decoded" / "outreach.db"
OUTREACH_DB.parent.mkdir(parents=True, exist_ok=True)

# Safety: don't email same author within this many days
COOLDOWN_DAYS = 90

# Minimum confidence to queue a connection for outreach
MIN_CONFIDENCE = 0.7


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(OUTREACH_DB))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS outreach_queue (
            id              INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id        TEXT NOT NULL,
            to_name         TEXT,
            to_email        TEXT,
            subject         TEXT NOT NULL,
            body            TEXT NOT NULL,
            connection_id   TEXT,
            paper_b_id      TEXT,
            status          TEXT NOT NULL DEFAULT 'pending_draft',
            -- statuses: 'pending_draft', 'drafted', 'approved', 'sent', 'failed', 'skipped'
            created_at      REAL NOT NULL,
            drafted_at      REAL,
            sent_at         REAL,
            error           TEXT,
            cost_usd        REAL DEFAULT 0.0,
            gmail_draft_id  TEXT
        );

        CREATE TABLE IF NOT EXISTS processed_connections (
            connection_id   TEXT PRIMARY KEY,
            paper_a_id      TEXT NOT NULL,
            paper_b_id      TEXT NOT NULL,
            queued_at       REAL NOT NULL,
            queue_id        INTEGER
        );

        CREATE TABLE IF NOT EXISTS unsubscribes (
            email       TEXT PRIMARY KEY,
            unsubscribed_at REAL NOT NULL,
            reason      TEXT
        );

        CREATE TABLE IF NOT EXISTS send_log (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            email       TEXT NOT NULL,
            paper_id    TEXT NOT NULL,
            sent_at     REAL NOT NULL,
            subject     TEXT
        );
        """
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Queue operations
# ---------------------------------------------------------------------------

def enqueue(email_data: dict[str, Any]) -> int:
    """Add an email to the outreach queue. Returns queue ID."""
    conn = _get_conn()

    to_email = email_data.get("to_email")
    if not to_email:
        logger.warning("No email address for paper %s — skipping", email_data.get("paper_id"))
        return -1

    # Check unsubscribe list
    if is_unsubscribed(to_email):
        logger.info("Skipping %s — unsubscribed", to_email)
        return -1

    # Check cooldown
    if _in_cooldown(to_email):
        logger.info("Skipping %s — in cooldown", to_email)
        return -1

    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO outreach_queue
            (paper_id, to_name, to_email, subject, body, connection_id, paper_b_id,
             status, created_at, cost_usd)
        VALUES (?, ?, ?, ?, ?, ?, ?, 'pending_draft', ?, ?)
        """,
        (
            email_data.get("paper_id", ""),
            email_data.get("to_name", ""),
            to_email,
            email_data.get("subject", ""),
            email_data.get("body", ""),
            email_data.get("connection_id", ""),
            email_data.get("paper_b_id", ""),
            time.time(),
            email_data.get("cost_usd", 0.0),
        ),
    )
    conn.commit()
    queue_id = cursor.lastrowid
    logger.info("Queued email %d for %s", queue_id, to_email)
    return queue_id


def enqueue_from_connection(
    connection_id: str,
    paper_a_id: str,
    paper_b_id: str,
    connection_type: str,
    confidence: float,
    description: str,
) -> bool:
    """Enqueue a connection for outreach processing. Returns True if newly queued.

    This creates a stub record (no email content yet) with status 'pending_draft'.
    The actual email is generated later via /api/outreach/draft/{id}.
    """
    if confidence < MIN_CONFIDENCE:
        return False

    conn = _get_conn()

    # Check if this connection was already processed
    existing = conn.execute(
        "SELECT 1 FROM processed_connections WHERE connection_id = ?",
        (connection_id,),
    ).fetchone()
    if existing:
        logger.debug("Connection %s already queued for outreach", connection_id[:8])
        return False

    # Insert stub — no email address yet, will be filled during draft generation
    cursor = conn.cursor()
    cursor.execute(
        """
        INSERT INTO outreach_queue
            (paper_id, to_name, to_email, subject, body, connection_id, paper_b_id,
             status, created_at, cost_usd)
        VALUES (?, '', NULL, '', '', ?, ?, 'pending_draft', ?, 0.0)
        """,
        (paper_a_id, connection_id, paper_b_id, time.time()),
    )
    queue_id = cursor.lastrowid

    conn.execute(
        """
        INSERT INTO processed_connections
            (connection_id, paper_a_id, paper_b_id, queued_at, queue_id)
        VALUES (?, ?, ?, ?, ?)
        """,
        (connection_id, paper_a_id, paper_b_id, time.time(), queue_id),
    )
    conn.commit()

    logger.info(
        "Queued connection %s for outreach (confidence %.0f%%, type=%s)",
        connection_id[:8], confidence * 100, connection_type,
    )
    return True


def get_pending_draft(limit: int = 20) -> list[dict]:
    """Get items in pending_draft status (need email generation)."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM outreach_queue WHERE status = 'pending_draft' ORDER BY created_at LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_pending(limit: int = 10) -> list[dict]:
    """Get pending emails awaiting approval/sending (drafted but not yet approved)."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM outreach_queue WHERE status IN ('pending_draft', 'drafted') ORDER BY created_at LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_drafted(limit: int = 20) -> list[dict]:
    """Get items with generated email content ready for Gmail draft creation."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM outreach_queue WHERE status = 'drafted' ORDER BY drafted_at LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_approved(limit: int = 1) -> list[dict]:
    """Get approved emails ready to send (one at a time)."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM outreach_queue WHERE status = 'approved' ORDER BY created_at LIMIT ?",
        (limit,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_item(queue_id: int) -> dict | None:
    conn = _get_conn()
    row = conn.execute(
        "SELECT * FROM outreach_queue WHERE id = ?",
        (queue_id,),
    ).fetchone()
    return dict(row) if row else None


def mark_drafted(queue_id: int, subject: str, body: str, to_name: str, to_email: str, cost_usd: float = 0.0) -> None:
    """Update a pending_draft item with generated email content."""
    conn = _get_conn()
    conn.execute(
        """UPDATE outreach_queue
           SET status = 'drafted', subject = ?, body = ?, to_name = ?, to_email = ?,
               cost_usd = cost_usd + ?, drafted_at = ?
           WHERE id = ?""",
        (subject, body, to_name, to_email, cost_usd, time.time(), queue_id),
    )
    conn.commit()


def approve(queue_id: int) -> None:
    """Mark an email as approved for sending."""
    conn = _get_conn()
    conn.execute(
        "UPDATE outreach_queue SET status = 'approved' WHERE id = ?",
        (queue_id,),
    )
    conn.commit()


def mark_sent(queue_id: int, gmail_draft_id: str | None = None) -> None:
    """Mark email as sent and log it."""
    conn = _get_conn()
    now = time.time()
    row = conn.execute(
        "SELECT to_email, paper_id, subject FROM outreach_queue WHERE id = ?",
        (queue_id,),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE outreach_queue SET status = 'sent', sent_at = ?, gmail_draft_id = ? WHERE id = ?",
            (now, gmail_draft_id, queue_id),
        )
        conn.execute(
            "INSERT INTO send_log (email, paper_id, sent_at, subject) VALUES (?, ?, ?, ?)",
            (row["to_email"], row["paper_id"], now, row["subject"]),
        )
        conn.commit()


def mark_failed(queue_id: int, error: str) -> None:
    conn = _get_conn()
    conn.execute(
        "UPDATE outreach_queue SET status = 'failed', error = ? WHERE id = ?",
        (error, queue_id),
    )
    conn.commit()


def mark_skipped(queue_id: int) -> None:
    """Mark an item as skipped (won't be drafted or sent)."""
    conn = _get_conn()
    conn.execute(
        "UPDATE outreach_queue SET status = 'skipped' WHERE id = ?",
        (queue_id,),
    )
    conn.commit()


# ---------------------------------------------------------------------------
# Unsubscribe
# ---------------------------------------------------------------------------

def unsubscribe(email: str, reason: str = "") -> None:
    """Add an email to the unsubscribe list."""
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO unsubscribes (email, unsubscribed_at, reason) VALUES (?, ?, ?)",
        (email.lower().strip(), time.time(), reason),
    )
    conn.commit()
    logger.info("Unsubscribed: %s", email)


def is_unsubscribed(email: str) -> bool:
    conn = _get_conn()
    row = conn.execute(
        "SELECT 1 FROM unsubscribes WHERE email = ?",
        (email.lower().strip(),),
    ).fetchone()
    return row is not None


def _in_cooldown(email: str) -> bool:
    """True if we've emailed this address within COOLDOWN_DAYS."""
    conn = _get_conn()
    cutoff = time.time() - (COOLDOWN_DAYS * 86400)
    row = conn.execute(
        "SELECT 1 FROM send_log WHERE email = ? AND sent_at > ?",
        (email.lower().strip(), cutoff),
    ).fetchone()
    return row is not None


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

def queue_stats() -> dict:
    conn = _get_conn()
    stats = {}
    for status in ("pending_draft", "drafted", "approved", "sent", "failed", "skipped"):
        row = conn.execute(
            "SELECT count(*) as n FROM outreach_queue WHERE status = ?",
            (status,),
        ).fetchone()
        stats[status] = row["n"]
    unsub_count = conn.execute("SELECT count(*) as n FROM unsubscribes").fetchone()["n"]
    stats["unsubscribed"] = unsub_count
    processed_count = conn.execute("SELECT count(*) as n FROM processed_connections").fetchone()["n"]
    stats["connections_processed"] = processed_count
    return stats
