"""Send the completed scan as a plain-text digest using authenticated SMTP over TLS."""

import os
import re
import smtplib
import ssl
from dataclasses import dataclass, field
from email.message import EmailMessage

from dotenv import dotenv_values


@dataclass(frozen=True)
class EmailDelivery:
    sender: str
    password: str = field(repr=False)
    recipient: str
    host: str
    port: int

    @classmethod
    def configured(cls) -> "EmailDelivery | None":
        """Load opt-in delivery settings, preferring environment variables."""
        settings = {**dotenv_values(".secrets/.env", encoding="utf-8-sig", interpolate=False),
                    **os.environ}
        enabled = (settings.get("EMAIL_ENABLED") or "false").strip().lower()
        if enabled == "false":
            return None
        if enabled != "true":
            raise ValueError("EMAIL_ENABLED must be true or false.")
        sender = (settings.get("EMAIL_FROM") or "").strip()
        recipient = (settings.get("EMAIL_TO") or "").strip()
        for name, value in (("EMAIL_FROM", sender), ("EMAIL_TO", recipient)):
            if not re.fullmatch(r"[^\s@,;<>]+@[^\s@,;<>]+\.[^\s@,;<>]+", value):
                raise ValueError(f"Set {name} to a single email address.")
        password = settings.get("SMTP_PASSWORD")
        if not password:
            raise ValueError("Set SMTP_PASSWORD for email delivery.")
        host = (settings.get("SMTP_HOST") or "smtp.gmail.com").strip()
        port = int(settings.get("SMTP_PORT") or "465")
        if not 1 <= port <= 65535:
            raise ValueError("SMTP_PORT must be between 1 and 65535.")
        return cls(sender, password, recipient, host, port)

    def send(self, lines: list[str]) -> None:
        """Submit one digest. Avoid automatic retries after an ambiguous response."""
        digest = EmailMessage()
        digest["From"] = self.sender
        digest["To"] = self.recipient
        digest["Subject"] = "School reminders — scan summary"
        digest.set_content("\n".join(lines))
        try:
            with smtplib.SMTP_SSL(self.host, self.port, timeout=30,
                                  context=ssl.create_default_context()) as smtp:
                smtp.login(self.sender, self.password)
                smtp.send_message(digest)
        except smtplib.SMTPAuthenticationError as error:
            raise ValueError("SMTP authentication failed. Check EMAIL_FROM and SMTP_PASSWORD.") from error
        except OSError as error:
            raise ValueError("Email delivery failed. Check SMTP settings and the recipient inbox before retrying.") from error
