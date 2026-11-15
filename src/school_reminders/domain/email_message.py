"""Email source evidence and derived body values."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class EmailMessage:
    """An email's source evidence and derived body text.

    Date headers and Gmail's millisecond receipt timestamp remain unmodified
    strings. ``text`` may be derived from HTML; ``raw_base64url`` is the original
    MIME source, including attachments, exactly as supplied by Gmail.
    """

    message_id: str
    thread_id: str
    internal_date_ms: str
    rfc_message_id: str
    sender: str
    subject: str
    date: str
    text: str
    html: str
    raw_base64url: str

    def to_dict(self) -> dict[str, str]:
        """Return the existing JSON export fields without transforming values."""
        return asdict(self)


