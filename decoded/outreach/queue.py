"""Outreach queue: thoughtful one-at-a-time sending with safety rails.

Features:
- SQLite-backed queue (independent of main Postgres DB)
- Rate limiting: one email per author per 90 days
- Unsubscribe tracking
- Dry-run mode (generate but don't send)
- Manual review before send
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


def _get_conn() -> sqlite3.Connection:
    conn = sqlite3.connect(str(OUTREACH_DB))
    conn.row_factory = sqlite3.Row
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS outreach_queue (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id    TEXT NOT NULL,
            to_name     TEXT,
            to_email    TEXT,
            subject     TEXT NOT NULL,
            body        TEXT NOT NULL,
            connection_id TEXT,
            status      TEXT NOT NULL DEFAULT 'pending',
            -- 'pending', 'approved', 'sent', 'failed', 'skipped'
            created_at  REAL NOT NULL,
            sent_at     REAL,
            error       TEXT,
            cost_usd    REAL DEFAULT 0.0
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
            (paper_id, to_name, to_email, subject, body, connection_id, status, created_at, cost_usd)
        VALUES (?, ?, ?, ?, ?, ?, 'pending', ?, ?)
        """,
        (
            email_data.get("paper_id", ""),
            email_data.get("to_name", ""),
            to_email,
            email_data.get("subject", ""),
            email_data.get("body", ""),
            email_data.get("connection_id", ""),
            time.time(),
            email_data.get("cost_usd", 0.0),
        ),
    )
    conn.commit()
    queue_id = cursor.lastrowid
    logger.info("Queued email %d for %s", queue_id, to_email)
    return queue_id


def get_pending(limit: int = 10) -> list[dict]:
    """Get pending emails awaiting approval/sending."""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM outreach_queue WHERE status = 'pending' ORDER BY created_at LIMIT ?",
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


def approve(queue_id: int) -> None:
    """Mark an email as approved for sending."""
    conn = _get_conn()
    conn.execute(
        "UPDATE outreach_queue SET status = 'approved' WHERE id = ?",
        (queue_id,),
    )
    conn.commit()


def mark_sent(queue_id: int) -> None:
    """Mark email as sent and log it."""
    conn = _get_conn()
    now = time.time()
    row = conn.execute(
        "SELECT to_email, paper_id, subject FROM outreach_queue WHERE id = ?",
        (queue_id,),
    ).fetchone()
    if row:
        conn.execute(
            "UPDATE outreach_queue SET status = 'sent', sent_at = ? WHERE id = ?",
            (now, queue_id),
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
    for status in ("pending", "approved", "sent", "failed", "skipped"):
        row = conn.execute(
            "SELECT count(*) as n FROM outreach_queue WHERE status = ?",
            (status,),
        ).fetchone()
        stats[status] = row["n"]
    unsub_count = conn.execute("SELECT count(*) as n FROM unsubscribes").fetchone()["n"]
    stats["unsubscribed"] = unsub_count
    return stats
