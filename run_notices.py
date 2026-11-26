"""Edit the inputs below and run this file in PyCharm to inspect extracted notices."""

from pprint import pprint
import os

from school_reminders.email.sway import canonical_sway_url
from school_reminders.extraction import parse_notices
from school_reminders.persistence import connect_database, save_manual_notices


EMAIL_SUBJECT = "Class trip"
EMAIL_CONTENT = """Oak should bring a hat on Friday."""
EMAIL_IS_HTML = False

# Paste a public Sway URL here to run the newsletter instead of the email.
SWAY_URL = "https://sway.cloud.microsoft/01GBWXHifUNfx21n?ref=email"


def parse_email_content(content: str, *, subject: str = "", html: bool = False) -> dict:
    """Parse a pasted email and return its notices and newsletter sources."""
    return parse_notices(content, subject=subject, html=html)


def parse_sway_url(url: str) -> dict:
    """Parse one public Sway newsletter and return its notices and source text."""
    canonical_url = canonical_sway_url(url)
    if canonical_url is None:
        raise ValueError("Provide a direct public Microsoft Sway URL.")
    return parse_notices(canonical_url)


if __name__ == "__main__":
    if SWAY_URL.strip():
        source_type = "sway"
        source_reference = canonical_sway_url(SWAY_URL) or SWAY_URL
        report = parse_sway_url(SWAY_URL)
        source_text = "\n\n".join(
            newsletter["text"] for newsletter in report["newsletters"].values()
        )
        subject = ""
    else:
        source_type = "pasted_email"
        source_reference = ""
        report = parse_email_content(EMAIL_CONTENT, subject=EMAIL_SUBJECT, html=EMAIL_IS_HTML)
        source_text = EMAIL_CONTENT
        subject = EMAIL_SUBJECT
    pprint(report["notices"], sort_dicts=False)
    if report["notices"]:
        with connect_database() as database:
            save_manual_notices(
                database, source_type=source_type, source_reference=source_reference,
                source_text=source_text, subject=subject, notices=report["notices"],
            )
        print("Validated notices saved to Supabase.")
