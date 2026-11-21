"""Command-line parsing, orchestration, and presentation for Gmail ingestion."""

import argparse
import json
import sys
from collections.abc import Sequence
from contextlib import ExitStack
from pathlib import Path
from tempfile import NamedTemporaryFile

from school_reminders.domain.email_message import EmailMessage
from school_reminders.email.gmail import connect, read_messages, validate_sender
from school_reminders.extraction import extract_notices
from school_reminders.groq_model import GroqNoticeModel


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read school emails from one Gmail sender.")
    parser.add_argument("--sender", required=True, help="Exact school sender email address")
    parser.add_argument("--limit", type=int, default=20, help="Maximum matching emails (default: 20)")
    parser.add_argument("--credentials", type=Path, default=Path(".secrets/credentials.json"))
    parser.add_argument("--token", type=Path, default=Path(".secrets/token.json"))
    parser.add_argument("--output", type=Path, help="Optional private JSON export, e.g. data/emails.json")
    parser.add_argument("--classify", action="store_true", help="Send subject and body text to Groq to extract notices")
    return parser


def _print_classification(message: EmailMessage, notices: Sequence[dict]) -> None:
    print(f"{message.date or '(no date)'} | {message.subject or '(no subject)'}")
    if not notices:
        print("  No notices identified.")
    for notice in notices:
        audience = notice["audience"]
        groups = list(audience["years"])
        groups.extend(f"{name} ({year})" for name, year in audience["class_years"].items())
        if audience["whole_school"]:
            groups.append("Whole school")
        label = ", ".join(groups) or "Audience unclear"
        if audience["review"]:
            label += " (needs review)"
        print(f"  - {notice['title']} | {label}")


def _export_messages(messages: Sequence[EmailMessage], output_path: Path, model: GroqNoticeModel | None) -> None:
    rows = []
    for message in messages:
        row: dict[str, object] = dict(message.to_dict())
        if model is not None:
            notices = extract_notices(model, message)
            row["notices"] = notices
            _print_classification(message, notices)
        rows.append(row)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with NamedTemporaryFile(dir=output_path.parent, delete=False) as temp:
        temporary_path = Path(temp.name)
    try:
        temporary_path.write_text(json.dumps(rows, indent=2, ensure_ascii=False), encoding="utf-8")
        temporary_path.replace(output_path)
    finally:
        temporary_path.unlink(missing_ok=True)


def _print_summary(messages: Sequence[EmailMessage]) -> None:
    print(f"Read {len(messages)} matching email(s).")
    for message in messages:
        print(f"{message.date} | {message.subject} | Gmail ID: {message.message_id}")


def main(argv: Sequence[str] | None = None) -> int:
    """Read matching emails and optionally export them; return the CLI exit code.

    ``None`` uses process arguments. Validation, local I/O, and missing dependency
    failures return 1; argparse usage errors exit with 2. Google API and OAuth
    failures propagate unchanged. No email content is printed beyond the summary.
    """
    parser = _build_parser()
    args = parser.parse_args(argv)
    try:
        if args.classify and not args.output:
            parser.error("--classify requires --output for the private classified report")
        sender = validate_sender(args.sender)
        if args.limit < 1:
            parser.error("--limit must be positive")
        with ExitStack() as resources:
            model = None
            if args.classify:
                model = resources.enter_context(GroqNoticeModel.open())
            service = connect(args.credentials, args.token)
            messages = read_messages(service, sender, args.limit)
            if args.output:
                _export_messages(messages, args.output, model)
            if args.classify:
                print(f"Processed {len(messages)} matching email(s) with Groq.")
            else:
                _print_summary(messages)
        return 0
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except ImportError:
        print('Missing dependencies. Run: python -m pip install -e "."', file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
