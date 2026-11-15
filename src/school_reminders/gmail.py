"""Read-only Gmail access and MIME message normalization."""

import base64
from dataclasses import asdict, dataclass
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from html.parser import HTMLParser
from pathlib import Path
import re

SCOPES = ["https://www.googleapis.com/auth/gmail.readonly"]


class _HTMLText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.hidden = 0

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style"}:
            self.hidden += 1
        if tag in {"br", "p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style"}:
            self.hidden = max(0, self.hidden - 1)
        if tag in {"p", "div", "li", "tr"}:
            self.parts.append("\n")

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


@dataclass(frozen=True)
class EmailMessage:
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

    def to_dict(self):
        return asdict(self)


def normalize_message(resource: dict) -> EmailMessage:
    raw = resource["raw"]
    message = BytesParser(policy=policy.default).parsebytes(
        base64.urlsafe_b64decode(raw + "=" * (-len(raw) % 4))
    )
    # get_body selects the body rather than attached text files or forwarded mail.
    plain_part = message.get_body(preferencelist=("plain",))
    html_part = message.get_body(preferencelist=("html",))
    plain = plain_part.get_content() if plain_part else ""
    html = html_part.get_content() if html_part else ""
    if not plain and html:
        parser = _HTMLText()
        parser.feed(html)
        plain = "".join(parser.parts).strip()
    return EmailMessage(
        message_id=resource["id"], thread_id=resource.get("threadId", ""),
        internal_date_ms=resource.get("internalDate", ""),
        rfc_message_id=str(message.get("Message-ID", "")),
        sender=str(message.get("From", "")), subject=str(message.get("Subject", "")),
        date=str(message.get("Date", "")), text=plain, html=html,
        raw_base64url=raw,
    )


def validate_sender(sender: str) -> str:
    sender = sender.strip()
    if not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", sender):
        raise ValueError("Provide a single sender email address, without a display name.")
    return sender


def connect(credentials_path: Path, token_path: Path):
    # Lazy imports keep parsing and unit tests independent of Google libraries.
    from google.auth.transport.requests import Request
    from google.oauth2.credentials import Credentials
    from google_auth_oauthlib.flow import InstalledAppFlow
    from googleapiclient.discovery import build

    credentials = None
    if token_path.exists():
        credentials = Credentials.from_authorized_user_file(str(token_path), SCOPES)
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(Request())
        else:
            if not credentials_path.is_file():
                raise FileNotFoundError(
                    f"OAuth credentials missing: {credentials_path}. See README.md for setup."
                )
            flow = InstalledAppFlow.from_client_secrets_file(str(credentials_path), SCOPES)
            credentials = flow.run_local_server(port=0)
        token_path.parent.mkdir(parents=True, exist_ok=True)
        token_path.write_text(credentials.to_json(), encoding="utf-8")
    return build("gmail", "v1", credentials=credentials, cache_discovery=False)


def read_messages(service, sender: str, limit: int = 20) -> list[EmailMessage]:
    sender = validate_sender(sender)
    if limit < 1:
        raise ValueError("Limit must be positive.")
    messages = []
    page_token = None
    while len(messages) < limit:
        page = service.users().messages().list(
            userId="me", q=f"from:({sender})", maxResults=min(500, limit - len(messages)),
            pageToken=page_token,
        ).execute()
        for item in page.get("messages", []):
            resource = service.users().messages().get(
                userId="me", id=item["id"], format="raw"
            ).execute()
            message = normalize_message(resource)
            # Gmail search can match aliases; verify the actual From address too.
            addresses = {address.casefold() for _, address in getaddresses([message.sender])}
            if sender.casefold() in addresses:
                messages.append(message)
        page_token = page.get("nextPageToken")
        if not page_token:
            break
    return messages
