"""Compatibility imports for the original Gmail module location.

New application code should import from school_reminders.email and domain.
"""

from school_reminders.domain.email_message import EmailMessage
from school_reminders.email.auth import SCOPES
from school_reminders.email.gmail import connect, read_messages, validate_sender
from school_reminders.email.mime import normalize_message

__all__ = ["SCOPES", "EmailMessage", "connect", "normalize_message", "read_messages", "validate_sender"]
