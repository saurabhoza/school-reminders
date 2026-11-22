import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from school_reminders.cli import main
from school_reminders.email.delivery import EmailDelivery


class EmailDeliveryTests(unittest.TestCase):
    def setUp(self):
        env = patch.dict(os.environ, dict(EMAIL_ENABLED="true", EMAIL_FROM="from@example.com",
                                         EMAIL_TO="family@example.com", SMTP_PASSWORD="test",
                                         SMTP_HOST="smtp.example.com", SMTP_PORT="465"))
        env.start()
        self.addCleanup(env.stop)
        files = patch("school_reminders.email.delivery.dotenv_values", return_value={})
        files.start()
        self.addCleanup(files.stop)

    def test_message(self):
        with patch("school_reminders.email.delivery.smtplib.SMTP_SSL") as connect:
            EmailDelivery.configured().send(["1 matching email(s).", "Trip | Maple (Year 4)"])
        smtp = connect.return_value.__enter__.return_value
        smtp.login.assert_called_once_with("from@example.com", "test")
        digest, = smtp.send_message.call_args.args
        self.assertEqual(digest["To"], "family@example.com")
        self.assertEqual(digest["From"], "from@example.com")
        self.assertIn("Maple (Year 4)", digest.get_content())
        self.assertFalse(digest.is_multipart())

    def test_disabled_and_invalid_address(self):
        with patch.dict(os.environ, {"EMAIL_ENABLED": "false"}):
            self.assertIsNone(EmailDelivery.configured())
        with patch.dict(os.environ, {"EMAIL_TO": "a@example.com,b@example.com"}), self.assertRaises(ValueError):
            EmailDelivery.configured()

    def test_sends_only_after_successful_export(self):
        with tempfile.TemporaryDirectory() as folder, patch("school_reminders.cli.connect"), patch(
            "school_reminders.cli.read_messages", return_value=[]
        ), patch.object(EmailDelivery, "send") as send, patch("builtins.print"):
            output = Path(folder) / "scan.json"
            args = ["--sender", "school@example.com", "--output", str(output)]
            def check_export(lines):
                self.assertEqual(output.read_text(), "[]")
                self.assertIn("0 matching email(s).", lines)
            send.side_effect = check_export
            self.assertEqual(main(args), 0)
            with patch("school_reminders.cli._export_messages", side_effect=OSError("failed")):
                self.assertEqual(main(args), 1)
            send.assert_called_once()

    def test_daily_digest_covers_london_clock_change(self):
        with patch("school_reminders.cli.connect") as connect, patch(
            "school_reminders.cli.read_messages", return_value=[]
        ) as read, patch.object(EmailDelivery, "send") as send, patch("builtins.print"):
            result = main(["--sender", "school@example.com", "--received-day", "2026-10-25",
                           "--non-interactive"])
        self.assertEqual(result, 0)
        self.assertIsNone(connect.call_args.args[0])
        self.assertIsNone(read.call_args.args[2])
        start, end = read.call_args.kwargs["received_between"]
        self.assertEqual(end - start, 25 * 3600)
        self.assertIn("0 matching email(s) received on 2026-10-25 (Europe/London).", send.call_args.args[0])
