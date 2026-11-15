"""Command-line interface for the first ingestion milestone."""

import argparse
import json
from pathlib import Path
import sys

from school_reminders.gmail import connect, read_messages, validate_sender


def main() -> int:
    parser = argparse.ArgumentParser(description="Read school emails from one Gmail sender.")
    parser.add_argument("--sender", required=True, help="Exact school sender email address")
    parser.add_argument("--limit", type=int, default=20, help="Maximum matching emails (default: 20)")
    parser.add_argument("--credentials", type=Path, default=Path(".secrets/credentials.json"))
    parser.add_argument("--token", type=Path, default=Path(".secrets/token.json"))
    parser.add_argument("--output", type=Path, help="Optional private JSON export, e.g. data/emails.json")
    args = parser.parse_args()
    try:
        sender = validate_sender(args.sender)
        if args.limit < 1:
            parser.error("--limit must be positive")
        service = connect(args.credentials, args.token)
        messages = read_messages(service, sender, args.limit)
        if args.output:
            args.output.parent.mkdir(parents=True, exist_ok=True)
            args.output.write_text(
                json.dumps([message.to_dict() for message in messages], indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        print(f"Read {len(messages)} matching email(s).")
        for message in messages:
            print(f"{message.date} | {message.subject} | Gmail ID: {message.message_id}")
        return 0
    except (ValueError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 1
    except ImportError:
        print('Missing dependencies. Run: python -m pip install -e "."', file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
