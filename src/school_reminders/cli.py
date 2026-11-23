"""Command-line parsing, orchestration, and presentation for Gmail ingestion."""

import argparse
import json
import os
import sys
from collections.abc import Sequence
from contextlib import ExitStack, nullcontext
from datetime import date, datetime, time, timedelta
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import TextIO
from zoneinfo import ZoneInfo

from school_reminders.domain.email_message import EmailMessage
from school_reminders.email.delivery import DeliveryAuthenticationError, EmailDelivery
from school_reminders.email.gmail import connect, read_messages, validate_sender
from school_reminders.email.sway import read_newsletters
from school_reminders.extraction import extract_notices
from school_reminders.groq_model import GroqNoticeModel
from school_reminders.persistence import connect_database, save_email_and_reminders


class _ScanProgress:
    """Flush scan events to the selected console stream."""

    def __init__(self, stream: TextIO) -> None:
        self.stream = stream
        self.diagnostic = "Scan failed."

    def report(self, message: str) -> None:
        print(f"[scan] {message}", file=self.stream, flush=True)

    def start(self, message: str, diagnostic: str) -> None:
        self.diagnostic = diagnostic
        self.report(message)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read school emails from one Gmail sender.")
    parser.add_argument("--sender", required=True, help="Exact school sender email address")
    parser.add_argument("--limit", type=int, help="Maximum matching emails (default: 20, or all for --received-day)")
    parser.add_argument("--received-day", type=date.fromisoformat, help="London receipt date in YYYY-MM-DD format")
    parser.add_argument("--non-interactive", action="store_true", help="Require an existing OAuth token")
    parser.add_argument("--safe-diagnostics", action="store_true", help="Report failures without private details")
    parser.add_argument("--detailed-logs", action="store_true", help="Include email subjects, dates and Groq replies in scan logs")
    parser.add_argument("--credentials", type=Path, default=Path(".secrets/credentials.json"))
    parser.add_argument("--token", type=Path, default=Path(".secrets/token.json"))
    parser.add_argument("--output", type=Path, help="Optional private JSON export, e.g. data/emails.json")
    parser.add_argument("--classify", action="store_true", help="Extract notices from email and linked Sway text with Groq")
    parser.add_argument("--store", action="store_true", help="Persist source emails and reminders in Supabase")
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
    progress: _ScanProgress | None = None, show_details: bool = True, detailed_logs: bool = False, database=None,
) -> list[str]:
    if progress is None:
        progress = _ScanProgress(sys.stderr)
    rows = []
    notice_lines = []
    for index, message in enumerate(messages, start=1):
        row: dict[str, object] = dict(message.to_dict())
        prefix = f"Email {index}/{len(messages)}"
        if detailed_logs:
            prefix += f" | {json.dumps(_email_heading(message), ensure_ascii=False)}"
            progress.report(f"Processing {prefix}")
        if model is not None:
            progress.start(f"{prefix}: checking linked Sway newsletters.", "Could not read linked Sway newsletters.")
            newsletters = read_newsletters(message)
            if newsletters:
                row["newsletters"] = newsletters
            progress.start(
                f"{prefix}: read {len(newsletters)} newsletter(s). Extracting notices and verifying evidence.",
                "Notice extraction or evidence verification failed. Check Groq availability.",
            )
            def report_call(event: str) -> None:
                progress.report(f"{prefix} | {event}")

            with model.trace_calls(report_call) if detailed_logs else nullcontext():
                notices = extract_notices(model, message, newsletters=newsletters)
            progress.report(f"{prefix}: extracted {len(notices)} verified notice(s).")
            row["notices"] = notices
            if database is not None:
                progress.start(f"{prefix}: saving to Supabase.", "Could not save email and reminders to Supabase.")
                save_email_and_reminders(database, message, notices)
                progress.report(f"{prefix}: saved to Supabase.")
            notice_lines.extend(_print_classification(message, notices, show_details=show_details))
        rows.append(row)
    progress.start("Writing private JSON export.", "Could not write the private export.")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=output_path.parent, delete=False) as temp:
        temporary_path = Path(temp.name)
    try:
        temporary_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)
    progress.report("Private JSON export written.")
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
    progress = _ScanProgress(sys.stdout if args.safe_diagnostics else sys.stderr)
    progress.start("Validating scan arguments.", "Invalid scan arguments. Check SCHOOL_SENDER and the receipt date.")
    try:
        if (args.classify or args.store) and not args.output:
            parser.error("--classify and --store require --output for the private report")
        if args.store and not args.classify:
            parser.error("--store requires --classify")
        sender = validate_sender(args.sender)
        if args.limit is not None and args.limit < 1:
            parser.error("--limit must be positive")
        progress.start("Checking digest delivery settings.", "Invalid email delivery settings. Check EMAIL_FROM, EMAIL_TO and SMTP_PORT.")
        delivery = EmailDelivery.configured()
        with ExitStack() as resources:
            model = None
            database = None
            if args.classify:
                progress.start("Initializing Groq.", "Could not initialize the Groq classifier. Check GROQ_API_KEY.")
                model = resources.enter_context(GroqNoticeModel.open())
            if args.store:
                progress.start("Connecting to Supabase.", "Could not connect to Supabase. Check SUPABASE_DB_URL.")
                database_url = os.environ.get("SUPABASE_DB_URL")
                if not database_url:
                    raise ValueError("Set SUPABASE_DB_URL to the Supabase Postgres connection string.")
                database = resources.enter_context(connect_database(database_url))
            progress.start("Connecting to Gmail with read-only OAuth.",
                           "Gmail OAuth setup or refresh failed. Check GMAIL_TOKEN_JSON and reauthorize locally if needed.")
            service = connect(None if args.non_interactive else args.credentials, args.token)
            progress.start("Reading matching Gmail messages.",
                           "Gmail read failed. Check that the Gmail API is enabled and the token has read-only Gmail access.")
            if args.received_day:
                zone = ZoneInfo("Europe/London")
                start = datetime.combine(args.received_day, time.min, zone)
                end = start + timedelta(days=1)
                messages = read_messages(service, sender, args.limit,
                                         received_between=(int(start.timestamp()), int(end.timestamp())))
            else:
                messages = read_messages(service, sender, args.limit or 20)
            progress.report(f"Found {len(messages)} matching email(s).")
            lines = []
            if args.output:
                lines = _export_messages(
                    messages, args.output, model, progress=progress, show_details=not args.safe_diagnostics,
                    detailed_logs=args.detailed_logs, database=database,
                )
            if args.classify:
                if not args.safe_diagnostics:
                    print(f"Processed {len(messages)} matching email(s) with Groq.")
            else:
                if not args.safe_diagnostics:
                    _print_summary(messages)
                lines = [_email_heading(message) for message in messages]
            progress.diagnostic = "Could not close scan resources."
        if delivery and messages:
            progress.start("Sending digest via SMTP.",
                           "SMTP delivery failed. Check SMTP_HOST and SMTP_PORT, then check your inbox before retrying.")
            period = f" received on {args.received_day} (Europe/London)" if args.received_day else ""
            delivery.send([f"{len(messages)} matching email(s){period}.", "", *lines])
            print("SMTP server accepted the scan digest.")
        elif delivery:
            if args.safe_diagnostics:
                progress.report("Skipping digest delivery because no emails matched.")
            else:
                print("No matching emails found. No digest sent.")
        else:
            progress.report("Digest delivery is disabled.")
        progress.report("Scan complete.")
        return 0
    except Exception as error:
        diagnostic = progress.diagnostic
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
