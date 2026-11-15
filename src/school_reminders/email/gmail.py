"""Read-only Gmail transport, sender filtering, and result pagination."""

from __future__ import annotations

import re
from email.utils import getaddresses
from pathlib import Path
from typing import TYPE_CHECKING, Any

from school_reminders.domain.email_message import EmailMessage
from school_reminders.email.auth import load_credentials
from school_reminders.email.mime import normalize_message

if TYPE_CHECKING:
    from googleapiclient.discovery import Resource

MAX_PAGE_SIZE = 500
SENDER_PATTERN = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


def validate_sender(sender: str) -> str:
    """Strip whitespace and validate the existing single-address input format.

    Raises:
        ValueError: If the input contains a display name or unsupported address.
    """
    sender = sender.strip()
    if not SENDER_PATTERN.fullmatch(sender):
        raise ValueError("Provide a single sender email address, without a display name.")
    return sender


def connect(credentials_path: Path, token_path: Path) -> Resource:
    """Build a Gmail client using cached, refreshed, or interactive credentials.

    May open a browser through OAuth. Google API errors are left intact for the
    caller; no mailbox writes are performed or authorized.
    """
    from googleapiclient.discovery import build

    credentials = load_credentials(credentials_path, token_path)
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def _get_message(messages_api: Any, message_id: str) -> EmailMessage:
    # Dynamic discovery methods and vendor payloads stay inside this adapter.
    resource = messages_api.get(userId="me", id=message_id, format="raw").execute()
    fields = {"id", "raw", "threadId", "internalDate"}
    if not isinstance(resource, dict):
        raise ValueError("Gmail returned an invalid message resource.")
    if not {"id", "raw"}.issubset(resource):
        raise ValueError("Gmail message is missing its ID or raw MIME source.")
    if any(not isinstance(value, str) for key, value in resource.items() if key in fields):
        raise ValueError("Gmail message metadata and MIME source must be strings.")
    return normalize_message({key: resource[key] for key in fields if key in resource})


def _matches_sender(message: EmailMessage, sender: str) -> bool:
    addresses = {address.casefold() for _, address in getaddresses([message.sender])}
    return sender.casefold() in addresses


def read_messages(service: Resource, sender: str, limit: int = 20) -> list[EmailMessage]:
    """Return up to ``limit`` emails whose From address matches ``sender``.

    Follows Gmail result pages, excluding spam/trash by the API default. Gmail
    search may match aliases, so each decoded From header is verified separately.
    The supplied client is owned by the caller. No messages are modified.

    Raises:
        ValueError: If sender/limit or a fetched message resource is invalid.
        HttpError: If a Gmail API request fails (propagated unchanged).
    """
    sender = validate_sender(sender)
    if limit < 1:
        raise ValueError("Limit must be positive.")

    messages: list[EmailMessage] = []
    page_token: str | None = None
    messages_api = service.users().messages()
    while len(messages) < limit:
        page = messages_api.list(
            userId="me",
            q=f"from:({sender})",
            maxResults=min(MAX_PAGE_SIZE, limit - len(messages)),
            pageToken=page_token,
        ).execute()
        for item in page.get("messages", []):
            message = _get_message(messages_api, item["id"])
            if _matches_sender(message, sender):
                messages.append(message)
        page_token = page.get("nextPageToken")
        if not page_token:
            break
    return messages
