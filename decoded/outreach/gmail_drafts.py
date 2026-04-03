"""Gmail draft creator via IMAP APPEND.

Creates Gmail drafts for outreach emails without requiring SMTP send permissions.
Uses IMAP APPEND to write directly into [Gmail]/Drafts.

Required env vars:
    GMAIL_FROM_EMAIL    — e.g. Drericwhitney@gmail.com
    GMAIL_APP_PASSWORD  — 16-char Google app password (not the account password)
                          Generate at: https://myaccount.google.com/apppasswords

Usage:
    from decoded.outreach.gmail_drafts import GmailDraftCreator
    creator = GmailDraftCreator()
    creator.create_draft(to_name, to_email, subject, body, outreach_id)
"""

from __future__ import annotations

import email.mime.multipart
import email.mime.text
import email.utils
import imaplib
import logging
import os
from pathlib import Path

from dotenv import load_dotenv

_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(_ROOT / ".env", override=True)

logger = logging.getLogger("decoded.outreach.gmail_drafts")

IMAP_HOST = "imap.gmail.com"
IMAP_PORT = 993
DRAFTS_FOLDER = "[Gmail]/Drafts"

FROM_NAME = "Dr. Eric Whitney, DO"


class GmailDraftCreator:
    """Creates Gmail drafts via IMAP APPEND for Eric's outreach account."""

    def __init__(
        self,
        from_email: str | None = None,
        app_password: str | None = None,
    ) -> None:
        self.from_email = from_email or os.environ.get("GMAIL_FROM_EMAIL", "Drericwhitney@gmail.com")
        self.app_password = app_password or os.environ.get("GMAIL_APP_PASSWORD", "")
        if not self.app_password:
            raise RuntimeError(
                "GMAIL_APP_PASSWORD not set. Generate one at "
                "https://myaccount.google.com/apppasswords and add it to .env"
            )

    def _build_message(self, to_name: str, to_email: str, subject: str, body: str) -> bytes:
        """Build a MIME message ready for IMAP APPEND."""
        msg = email.mime.multipart.MIMEMultipart("alternative")
        msg["From"] = email.utils.formataddr((FROM_NAME, self.from_email))
        msg["To"] = email.utils.formataddr((to_name, to_email))
        msg["Subject"] = subject
        msg["Date"] = email.utils.formatdate(localtime=True)
        msg["Message-ID"] = email.utils.make_msgid(domain=self.from_email.split("@")[-1])

        # Plain text only — Gmail renders it fine, keeps emails natural
        part = email.mime.text.MIMEText(body, "plain", "utf-8")
        msg.attach(part)
        return msg.as_bytes()

    def create_draft(
        self,
        to_name: str,
        to_email: str,
        subject: str,
        body: str,
        outreach_id: int | None = None,
    ) -> None:
        """Append message to Gmail Drafts folder.

        Raises on connection/auth failure. Caller should catch and handle.
        """
        raw = self._build_message(to_name, to_email, subject, body)

        with imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT) as imap:
            imap.login(self.from_email, self.app_password)

            # APPEND flags=() means no special flags — draft behavior is folder-based in Gmail
            typ, data = imap.append(DRAFTS_FOLDER, "", imaplib.Time2Internaldate(None), raw)
            if typ != "OK":
                raise RuntimeError(f"IMAP APPEND failed: {typ} {data}")

        label = f"outreach_id={outreach_id}" if outreach_id is not None else ""
        logger.info("Gmail draft created → %s <%s> %s", to_name, to_email, label)

    @classmethod
    def is_configured(cls) -> bool:
        """True if the Gmail app password is available in the environment."""
        return bool(os.environ.get("GMAIL_APP_PASSWORD"))
