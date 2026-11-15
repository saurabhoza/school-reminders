"""Pure MIME normalization, without Gmail I/O."""

import base64
from collections.abc import Mapping
from email import policy
from email.message import EmailMessage as MIMEMessage
from email.parser import BytesParser
from html.parser import HTMLParser

from school_reminders.domain.email_message import EmailMessage


class _HTMLTextParser(HTMLParser):
    """Extract readable body text while omitting script and style content."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.hidden_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in {"script", "style"}:
            self.hidden_depth += 1
        if tag in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in {"script", "style"}:
            self.hidden_depth = max(0, self.hidden_depth - 1)
        if tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if not self.hidden_depth:
            self.parts.append(data)


def _body_content(message: MIMEMessage, subtype: str) -> str:
    part = message.get_body(preferencelist=(subtype,))
    if part is None:
        return ""
    content = part.get_content()
    if not isinstance(content, str):
        raise ValueError(f"Expected text content for MIME body subtype {subtype}.")
    return content


def normalize_message(resource: Mapping[str, str]) -> EmailMessage:
    """Decode a raw Gmail message, preferring plain text over HTML-derived text.

    Requires ``id`` and ``raw``; missing optional metadata stays empty.
    Attached text files are not selected as the message body. Original source
    is preserved independently of decoded and derived values.
    """
    raw = resource["raw"]
    source = base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    message = BytesParser(_class=MIMEMessage, policy=policy.default).parsebytes(source)
    plain = _body_content(message, "plain")
    html = _body_content(message, "html")
    if not plain and html:
        parser = _HTMLTextParser()
        parser.feed(html)
        plain = "".join(parser.parts).strip()

    return EmailMessage(
        message_id=resource["id"],
        thread_id=resource.get("threadId", ""),
        internal_date_ms=resource.get("internalDate", ""),
        rfc_message_id=str(message.get("Message-ID", "")),
        sender=str(message.get("From", "")),
        subject=str(message.get("Subject", "")),
        date=str(message.get("Date", "")),
        text=plain,
        html=html,
        raw_base64url=raw,
    )
