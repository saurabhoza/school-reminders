"""Persist validated email sources and extracted reminders to Supabase Postgres."""

from __future__ import annotations

import json
from datetime import datetime, timezone
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
    with connection.transaction():
        connection.execute(
            """
            INSERT INTO source_emails
                (gmail_message_id, thread_id, sender, subject, received_at, rfc_message_id)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (gmail_message_id) DO UPDATE SET
                thread_id = EXCLUDED.thread_id,
                sender = EXCLUDED.sender,
                subject = EXCLUDED.subject,
                received_at = EXCLUDED.received_at,
                rfc_message_id = EXCLUDED.rfc_message_id
            """,
            (message.message_id, message.thread_id, message.sender, message.subject,
             received_at, message.rfc_message_id),
        )
        for index, notice in enumerate(notices):
            audience = notice["audience"]
            years = list(audience["years"])
            if audience["whole_school"]:
                years = ["Whole school"]
            connection.execute(
                """
                INSERT INTO reminders
                    (gmail_message_id, notice_index, title, event_date_text, years, classes,
                     date_evidence, evidence, audience_evidence, review_required, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s, 'pending')
                ON CONFLICT (gmail_message_id, notice_index) DO UPDATE SET
                    title = EXCLUDED.title,
                    event_date_text = EXCLUDED.event_date_text,
                    years = EXCLUDED.years,
                    classes = EXCLUDED.classes,
                    date_evidence = EXCLUDED.date_evidence,
                    evidence = EXCLUDED.evidence,
                    audience_evidence = EXCLUDED.audience_evidence,
                    review_required = EXCLUDED.review_required
                """,
                (message.message_id, index, notice["title"], notice["event_date"],
                 years, audience["classes"], json.dumps(notice["date_evidence"]),
                 json.dumps(notice["evidence"]), json.dumps(notice["audience_evidence"]),
                 audience["review"]),
            )


def connect_database(database_url: str) -> Connection:
    """Open one short-lived Postgres connection for a scheduled scan."""
    import psycopg

    return psycopg.connect(database_url, connect_timeout=15)
