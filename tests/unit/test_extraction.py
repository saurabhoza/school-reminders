import json
import tempfile
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from io import StringIO
from pathlib import Path
from unittest.mock import patch

import httpx
from school_reminders.groq_model import GroqNoticeModel

from school_reminders.cli import _print_classification, main
from school_reminders.extraction import extract_notices
from school_reminders.gmail import normalize_message
from test_gmail import resource


class ExtractionTests(unittest.TestCase):
    def setUp(self):
        self.message = normalize_message(resource(
            '<head><title>hidden</title></head><p>Oak</p><p>Bring hats &amp; coats.</p>'
            '<a href="https://example.org/private">All classes finish early.</a>', "text/html",
        ))
        self.notice = dict(title="Bring outdoor clothes", years=[], classes=["Oak"],
                           whole_school=False, review=False,
                           evidence=[dict(segment=2, quote="hats &amp; coats")],
                           audience_evidence=[dict(segment=1, quote="Oak")])
        self.result = {"notices": [self.notice]}
        self.responses = iter(())
        self.requests = []
        http_client = httpx.Client(transport=httpx.MockTransport(self.respond))
        self.addCleanup(http_client.close)
        with patch.dict("os.environ", {"GROQ_API_KEY": "synthetic"}):
            self.model = GroqNoticeModel(http_client)

    def respond(self, request):
        self.requests.append(json.loads(request.content))
        return httpx.Response(200, json={
            "id": "test", "created": 0, "model": "test", "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(next(self.responses, self.result))}}],
        })

    def test_whole_email_request_and_source_evidence(self):
        self.result["notices"].append(dict(self.notice, title="Early finish", classes=[],
            whole_school=True, evidence=[dict(segment=3, quote="All classes finish early.")],
            audience_evidence=[dict(segment=3, quote="All classes")]))
        oak, school = extract_notices(self.model, self.message)
        self.assertEqual(oak["audience"]["class_years"], {"Oak": "Year 4"})
        self.assertTrue(school["audience"]["whole_school"])
        quote = oak["evidence"][0]
        self.assertEqual(self.message.html[quote["start"]:quote["end"]], "hats &amp; coats")
        request, = self.requests
        system, email = request["messages"]
        self.assertEqual(system["role"], "system")
        self.assertEqual([s["text"] for s in json.loads(email["content"])],
                         ["Year 4 trip", "Oak", "Bring hats &amp; coats.", "All classes finish early."])
        self.assertTrue(request["response_format"]["json_schema"]["strict"])

    def test_invalid_evidence_roster_and_structure(self):
        for change in ({"evidence": [dict(segment=2, quote="invented")]},
                       {"classes": ["Unknown"]}, {"review": "yes"},
                       {"audience_evidence": []}, {"whole_school": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.result = {"notices": [dict(self.notice, **change)]}
                extract_notices(self.model, self.message)

    def test_ambiguous_and_empty_results(self):
        self.notice.update(classes=[], audience_evidence=[])
        self.assertTrue(extract_notices(self.model, self.message)[0]["audience"]["review"])
        self.result = {"notices": []}
        self.assertEqual(extract_notices(self.model, self.message), [])

    def test_corrects_each_reported_evidence_failure_once(self):
        for change in ({"evidence": [dict(segment=2, quote="hats & coats")]},
                       {"audience_evidence": []}):
            with self.subTest(change=change):
                self.requests.clear()
                self.responses = iter([{"notices": [dict(self.notice, **change)]}, self.result])
                notice, = extract_notices(self.model, self.message)
                self.assertEqual(notice["evidence"][0]["quote"], "hats &amp; coats")
                self.assertEqual(len(self.requests), 2)
                self.assertIn("previous report failed", self.requests[1]["messages"][0]["content"])
                payload = json.loads(self.requests[1]["messages"][1]["content"])
                self.assertEqual([part["segment"] for part in payload], list(range(len(payload))))

    def test_rejects_repeatedly_unsupported_audience(self):
        self.notice["audience_evidence"] = []
        with self.assertRaisesRegex(ValueError, "without evidence"):
            extract_notices(self.model, self.message)
        self.assertEqual(len(self.requests), 2)

    def test_cli_preserves_report_on_failure_and_skips_groq_for_plain_export(self):
        with tempfile.TemporaryDirectory() as tmp, patch("school_reminders.cli.connect"), patch(
            "school_reminders.cli.read_messages", return_value=[self.message]
        ), patch("school_reminders.cli.GroqNoticeModel.open") as client, patch("builtins.print") as display, patch.dict(
            "os.environ", {"GROQ_API_KEY": "synthetic", "EMAIL_ENABLED": "false"}
        ):
            client.return_value.__enter__.return_value = self.model
            output = Path(tmp) / "report.json"
            args = ["--sender", "school@example.com", "--output", str(output)]
            self.assertEqual(main(args), 0)
            client.assert_not_called()
            self.assertEqual(main(args + ["--classify"]), 0)
            display.assert_any_call("(no date) | Year 4 trip")
            display.assert_any_call("  - Bring outdoor clothes | Oak (Year 4)")
            previous = output.read_bytes()
            self.assertEqual(json.loads(previous)[0]["message_id"], self.message.message_id)
            self.result = {"unexpected": True}
            self.assertEqual(main(args + ["--classify"]), 1)
            self.assertEqual(output.read_bytes(), previous)

    def test_display_mixed_audiences_and_empty_messages(self):
        self.result["notices"].extend([
            dict(self.notice, classes=[], years=["Year 4"]),
            dict(self.notice, classes=[], whole_school=True),
            dict(self.notice, classes=[], review=True, audience_evidence=[]),
        ])
        notices = extract_notices(self.model, self.message)
        output = StringIO()
        with redirect_stdout(output):
            _print_classification(replace(self.message, date="20 Nov 2026"), notices)
            _print_classification(replace(self.message, subject="Second email"), [])
        lines = output.getvalue().splitlines()
        self.assertEqual(lines[0], "20 Nov 2026 | Year 4 trip")
        self.assertEqual([line.split(" | ")[1] for line in lines[1:5]],
                         ["Oak (Year 4)", "Year 4", "Whole school", "Audience unclear (needs review)"])
        self.assertEqual(lines[5:], ["(no date) | Second email", "  No notices identified."])
