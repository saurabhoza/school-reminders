"""Command-line parsing, orchestration, and presentation for Gmail ingestion."""

import argparse
import json
import sys
from collections.abc import Sequence
from pathlib import Path

from school_reminders.gmail import connect, read_messages, validate_sender
from school_reminders.messages import EmailMessage


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Read school emails from one Gmail sender.")
    parser.add_argument("--sender", required=True, help="Exact school sender email address")
    parser.add_argument("--limit", type=int, default=20, help="Maximum matching emails (default: 20)")
    parser.add_argument("--credentials", type=Path, default=Path(".secrets/credentials.json"))
    parser.add_argument("--token", type=Path, default=Path(".secrets/token.json"))
    parser.add_argument("--output", type=Path, help="Optional private JSON export, e.g. data/emails.json")
    return parser


def _export_messages(messages: Sequence[EmailMessage], output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(
        json.dumps([message.to_dict() for message in messages], indent=2, ensure_ascii=False),
        encoding="utf-8",
    )


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
        sender = validate_sender(args.sender)
        if args.limit < 1:
            parser.error("--limit must be positive")
        service = connect(args.credentials, args.token)
        messages = read_messages(service, sender, args.limit)
        if args.output:
            _export_messages(messages, args.output)
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
