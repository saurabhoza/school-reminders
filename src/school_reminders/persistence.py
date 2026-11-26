"""Persist validated email sources and extracted reminders to Supabase Postgres."""

from __future__ import annotations

import json
import hashlib
import runpy
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import TYPE_CHECKING

from school_reminders.domain.email_message import EmailMessage

if TYPE_CHECKING:
    from psycopg import Connection


def save_email_and_reminders(
    connection: Connection,
    message: EmailMessage,
    notices: list[dict],
) -> None:
    """Upsert a source email and its validated notices in one transaction."""
    received_at = datetime.fromtimestamp(int(message.internal_date_ms) / 1000, timezone.utc)
    _save_source_and_reminders(
        connection, source_key=message.message_id, source_type="gmail",
        gmail_message_id=message.message_id, source_reference=message.message_id,
        source_text=message.text, thread_id=message.thread_id, sender=message.sender,
        subject=message.subject, received_at=received_at, rfc_message_id=message.rfc_message_id,
        notices=notices,
    )


def save_manual_notices(
    connection: Connection, *, source_type: str, source_reference: str,
    source_text: str, subject: str, notices: list[dict],
) -> None:
    """Save notices parsed from pasted email text or a public Sway URL."""
    identity = f"{source_type}\0{source_reference}\0{subject}\0{source_text}"
    source_key = f"{source_type}:{hashlib.sha256(identity.encode('utf-8')).hexdigest()}"
    _save_source_and_reminders(
        connection, source_key=source_key, source_type=source_type, gmail_message_id=None,
        source_reference=source_reference, source_text=source_text, thread_id="", sender="",
        subject=subject, received_at=None, rfc_message_id="", notices=notices,
    )


def _save_source_and_reminders(
    connection: Connection, *, source_key: str, source_type: str,
    gmail_message_id: str | None, source_reference: str, source_text: str,
    thread_id: str, sender: str, subject: str, received_at: datetime | None,
    rfc_message_id: str, notices: list[dict],
) -> None:
    """Upsert a source and its validated notices in one transaction."""
    stored_gmail_message_id = gmail_message_id or str(uuid.uuid4())
    with connection.transaction():
        source_row = connection.execute(
            """
            INSERT INTO source_emails
                (source_key, source_type, gmail_message_id, source_reference, source_text,
                 thread_id, sender, subject, received_at, rfc_message_id)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
            ON CONFLICT (source_key) DO UPDATE SET
                source_text = EXCLUDED.source_text,
                source_reference = EXCLUDED.source_reference,
                thread_id = EXCLUDED.thread_id,
                sender = EXCLUDED.sender,
                subject = EXCLUDED.subject,
                received_at = EXCLUDED.received_at,
                rfc_message_id = EXCLUDED.rfc_message_id
            RETURNING gmail_message_id
            """,
            (source_key, source_type, stored_gmail_message_id, source_reference, source_text,
             thread_id, sender, subject, received_at, rfc_message_id),
        ).fetchone()
        if source_row is None:
            raise RuntimeError("Supabase did not return the saved source row.")
        stored_gmail_message_id = source_row[0]
        for index, notice in enumerate(notices):
            audience = notice["audience"]
            years = list(audience["years"])
            if audience["whole_school"]:
                years = ["Whole school"]
            connection.execute(
                """
                INSERT INTO reminders
                    (gmail_message_id, source_key, notice_index, title, event_date_text, years, classes,
                     date_evidence, evidence, audience_evidence, review_required, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, 'pending')
                ON CONFLICT (source_key, notice_index) DO UPDATE SET
                    gmail_message_id = EXCLUDED.gmail_message_id,
                    title = EXCLUDED.title,
                    event_date_text = EXCLUDED.event_date_text,
                    years = EXCLUDED.years,
                    classes = EXCLUDED.classes,
                    date_evidence = EXCLUDED.date_evidence,
                    evidence = EXCLUDED.evidence,
                    audience_evidence = EXCLUDED.audience_evidence,
                    review_required = EXCLUDED.review_required
                """,
                (stored_gmail_message_id, source_key, index, notice["title"], notice["event_date"],
                 years, audience["classes"], json.dumps(notice["date_evidence"]),
                 json.dumps(notice["evidence"]), json.dumps(notice["audience_evidence"]),
                 audience["review"]),
            )


def connect_database() -> Connection:
    """Open one short-lived Postgres connection for a scheduled scan."""
    import psycopg

    configuration_path = Path(".secrets/supabase_config.py")
    if not configuration_path.is_file():
        raise FileNotFoundError("Create .secrets/supabase_config.py with SUPABASE_DB_URL.")
    configuration = runpy.run_path(str(configuration_path))
    database_url = configuration.get("SUPABASE_DB_URL")
    if not isinstance(database_url, str) or not database_url.startswith(("postgresql://", "postgres://")):
        raise ValueError("SUPABASE_DB_URL must be a PostgreSQL connection string from Supabase Connect.")
    return psycopg.connect(database_url, connect_timeout=15)
