import base64
import unittest
from unittest.mock import MagicMock

from school_reminders.gmail import normalize_message, read_messages, validate_sender


def resource(body, content_type="text/plain", sender="School <school@example.com>"):
    raw = (f"From: {sender}\r\nSubject: Year 4 trip\r\n"
           f"Content-Type: {content_type}; charset=utf-8\r\n\r\n{body}").encode()
    return {"id": "m1", "threadId": "t1", "internalDate": "123",
            "raw": base64.urlsafe_b64encode(raw).decode().rstrip("=")}


class GmailTests(unittest.TestCase):
    def test_plain_text_and_source(self):
        original = resource("Bring a coat.")
        email = normalize_message(original)
        self.assertEqual(email.text, "Bring a coat.")
        self.assertEqual(email.raw_base64url, original["raw"])

    def test_html_fallback(self):
        email = normalize_message(resource("<p>Year 4 &amp; friends</p><script>hidden</script>", "text/html"))
        self.assertEqual(email.text, "Year 4 & friends")

    def test_pagination_and_sender_verification(self):
        service = MagicMock()
        api = service.users.return_value.messages.return_value
        api.list.return_value.execute.side_effect = [
            {"messages": [{"id": "other"}], "nextPageToken": "next"},
            {"messages": [{"id": "m1"}]},
        ]
        api.get.return_value.execute.side_effect = [
            resource("Other", sender="alias@example.com"), resource("Trip"),
        ]
        self.assertEqual([m.text for m in read_messages(service, "school@example.com", 1)], ["Trip"])
        self.assertEqual(api.list.call_args.kwargs["pageToken"], "next")

    def test_empty_mailbox(self):
        service = MagicMock()
        service.users.return_value.messages.return_value.list.return_value.execute.return_value = {}
        self.assertEqual(read_messages(service, "school@example.com"), [])

    def test_invalid_input(self):
        with self.assertRaises(ValueError):
            validate_sender("school@example.com OR from:other@example.com")
        with self.assertRaises(ValueError):
            read_messages(None, "school@example.com", 0)
