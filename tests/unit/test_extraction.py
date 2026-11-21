import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx
from school_reminders.groq_model import GroqNoticeModel

from school_reminders.cli import main
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
                "role": "assistant", "content": json.dumps(self.result)}}],
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

    def test_cli_preserves_report_on_failure_and_skips_groq_for_plain_export(self):
        with tempfile.TemporaryDirectory() as tmp, patch("school_reminders.cli.connect"), patch(
            "school_reminders.cli.read_messages", return_value=[self.message]
        ), patch("school_reminders.cli.GroqNoticeModel.open") as client, patch("builtins.print"), patch.dict(
            "os.environ", {"GROQ_API_KEY": "synthetic"}
        ):
            client.return_value.__enter__.return_value = self.model
            output = Path(tmp) / "report.json"
            args = ["--sender", "school@example.com", "--output", str(output)]
            self.assertEqual(main(args), 0)
            client.assert_not_called()
            self.assertEqual(main(args + ["--classify"]), 0)
            previous = output.read_bytes()
            self.assertEqual(json.loads(previous)[0]["message_id"], self.message.message_id)
            self.result = {"unexpected": True}
            self.assertEqual(main(args + ["--classify"]), 1)
            self.assertEqual(output.read_bytes(), previous)
