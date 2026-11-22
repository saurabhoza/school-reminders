"""Edit the inputs below and run this file in PyCharm to inspect extracted notices."""

from pprint import pprint

from school_reminders.email.sway import canonical_sway_url
from school_reminders.extraction import parse_notices


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
        report = parse_sway_url(SWAY_URL)
    else:
        report = parse_email_content(EMAIL_CONTENT, subject=EMAIL_SUBJECT, html=EMAIL_IS_HTML)
    pprint(report["notices"], sort_dicts=False)
