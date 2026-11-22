"""Command-line parsing, orchestration, and presentation for Gmail ingestion."""

import argparse
import json
import sys
from collections.abc import Sequence
from contextlib import ExitStack
from datetime import date, datetime, time, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from zoneinfo import ZoneInfo

from school_reminders.domain.email_message import EmailMessage
from school_reminders.email.delivery import DeliveryAuthenticationError, EmailDelivery
from school_reminders.email.gmail import connect, read_messages, validate_sender
from school_reminders.email.sway import read_newsletters
from school_reminders.extraction import extract_notices
from school_reminders.groq_model import GroqNoticeModel


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read school emails from one Gmail sender.")
    parser.add_argument("--sender", required=True, help="Exact school sender email address")
    parser.add_argument("--limit", type=int, help="Maximum matching emails (default: 20, or all for --received-day)")
    parser.add_argument("--received-day", type=date.fromisoformat, help="London receipt date in YYYY-MM-DD format")
    parser.add_argument("--non-interactive", action="store_true", help="Require an existing OAuth token")
    parser.add_argument("--safe-diagnostics", action="store_true", help="Report failures without private details")
    parser.add_argument("--credentials", type=Path, default=Path(".secrets/credentials.json"))
    parser.add_argument("--token", type=Path, default=Path(".secrets/token.json"))
    parser.add_argument("--output", type=Path, help="Optional private JSON export, e.g. data/emails.json")
    parser.add_argument("--classify", action="store_true", help="Extract notices from email and linked Sway text with Groq")
    return parser


def _email_heading(message: EmailMessage) -> str:
    return f"{message.date or '(no date)'} | {message.subject or '(no subject)'}"


def _print_classification(
    message: EmailMessage, notices: Sequence[dict], *, show_details: bool = True,
) -> list[str]:
    lines = [_email_heading(message)]
    if not notices:
        lines.append("  No notices identified.")
    for notice in notices:
        audience = notice["audience"]
        groups = list(audience["years"])
        groups.extend(f"{name} ({year})" for name, year in audience["class_years"].items())
        if audience["whole_school"]:
            groups.append("Whole school")
        label = ", ".join(groups) or "Audience unclear"
        if audience["review"]:
            label += " (needs review)"
        lines.append(f"  - {notice['event_date']} — {notice['title']} | {label}")
    if show_details:
        for line in lines:
            print(line)
    return lines


def _export_messages(
    messages: Sequence[EmailMessage], output_path: Path, model: GroqNoticeModel | None, *,
    show_details: bool = True,
) -> list[str]:
    rows = []
    notice_lines = []
    for message in messages:
        row: dict[str, object] = dict(message.to_dict())
        if model is not None:
            newsletters = read_newsletters(message)
            if newsletters:
                row["newsletters"] = newsletters
            notices = extract_notices(model, message, newsletters=newsletters)
            row["notices"] = notices
            notice_lines.extend(_print_classification(message, notices, show_details=show_details))
        rows.append(row)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=output_path.parent, delete=False) as temp:
        temporary_path = Path(temp.name)
    try:
        temporary_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    return notice_lines


def _print_summary(messages: Sequence[EmailMessage]) -> None:
    print(f"Read {len(messages)} matching email(s).")
    for message in messages:
        print(f"{message.date} | {message.subject} | Gmail ID: {message.message_id}")


def main(argv: Sequence[str] | None = None) -> int:
    """Read matching emails and optionally export them; return the CLI exit code.

    ``None`` uses process arguments. Validation, local I/O, and missing dependency
    failures return 1; argparse usage errors exit with 2. Google API and OAuth
    failures propagate unchanged in the local CLI. Safe diagnostics report
    only fixed failure messages and suppress mail details.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    diagnostic = "Invalid scan arguments. Check SCHOOL_SENDER and the receipt date."
    try:
        if args.classify and not args.output:
            parser.error("--classify requires --output for the private classified report")
        sender = validate_sender(args.sender)
        if args.limit is not None and args.limit < 1:
            parser.error("--limit must be positive")
        diagnostic = "Invalid email delivery settings. Check EMAIL_FROM, EMAIL_TO and SMTP_PORT."
        delivery = EmailDelivery.configured()
        with ExitStack() as resources:
            model = None
            if args.classify:
                diagnostic = "Could not initialize the Groq classifier. Check GROQ_API_KEY."
                model = resources.enter_context(GroqNoticeModel.open())
            diagnostic = "Gmail OAuth setup or refresh failed. Check GMAIL_TOKEN_JSON and reauthorize locally if needed."
            service = connect(None if args.non_interactive else args.credentials, args.token)
            diagnostic = "Gmail read failed. Check that the Gmail API is enabled and the token has read-only Gmail access."
            if args.received_day:
                zone = ZoneInfo("Europe/London")
                start = datetime.combine(args.received_day, time.min, zone)
                end = start + timedelta(days=1)
                messages = read_messages(service, sender, args.limit,
                                         received_between=(int(start.timestamp()), int(end.timestamp())))
            else:
                messages = read_messages(service, sender, args.limit or 20)
            lines = []
            if args.output:
                diagnostic = (
                    "Notice classification or export failed. Check Groq availability and linked Sway access."
                    if args.classify else "Could not write the private export."
                )
                lines = _export_messages(messages, args.output, model, show_details=not args.safe_diagnostics)
            if args.classify:
                if not args.safe_diagnostics:
                    print(f"Processed {len(messages)} matching email(s) with Groq.")
            else:
                if not args.safe_diagnostics:
                    _print_summary(messages)
                lines = [_email_heading(message) for message in messages]
        if delivery:
            diagnostic = "SMTP delivery failed. Check SMTP_HOST and SMTP_PORT, then check your inbox before retrying."
            period = f" received on {args.received_day} (Europe/London)" if args.received_day else ""
            delivery.send([f"{len(messages)} matching email(s){period}.", "", *lines])
            print("SMTP server accepted the scan digest.")
        return 0
    except Exception as error:
        if isinstance(error, ImportError):
            diagnostic = 'Missing dependencies. Run: python -m pip install -e "."'
        elif args.safe_diagnostics and isinstance(error, DeliveryAuthenticationError):
            diagnostic = "SMTP authentication failed. Check EMAIL_FROM and SMTP_PASSWORD."
        elif not args.safe_diagnostics:
            if not isinstance(error, (ValueError, OSError)):
                raise
            diagnostic = str(error)
        print(f"Error: {diagnostic}", file=sys.stdout if args.safe_diagnostics else sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
