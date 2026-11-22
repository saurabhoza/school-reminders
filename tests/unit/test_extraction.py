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

from school_reminders.cli import _export_messages, _print_classification, main
from school_reminders.extraction import extract_notices, parse_notices
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
        result = next(self.responses, self.result)
        if isinstance(result, httpx.Response):
            return result
        return httpx.Response(200, json={
            "id": "test", "created": 0, "model": "test", "object": "chat.completion",
            "choices": [{"index": 0, "finish_reason": "stop", "message": {
                "role": "assistant", "content": json.dumps(result)}}],
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

    def test_parse_pasted_email_and_standalone_sway(self):
        text = "  Oak should bring hats."
        url = "https://sway.cloud.microsoft/SyntheticIssue"
        snapshots = {"newsletter_1": {"url": url, "text": text}}
        with patch.object(GroqNoticeModel, "open") as open_model:
            open_model.return_value.__enter__.return_value = self.model
            for content, options, field, index in [
                (text, {"subject": "Class trip"}, "text", 1),
                (f"<p>{text}</p>", {"html": True}, "html", 0),
                (url, {}, "newsletter_1", 0),
            ]:
                self.notice.update(evidence=[dict(segment=index, quote="bring hats")],
                                   audience_evidence=[dict(segment=index, quote="Oak")])
                with self.subTest(field=field), patch(
                    "school_reminders.extraction.newsletters_from_content",
                    return_value=snapshots if content == url else {},
                ) as read:
                    report = parse_notices(content, **options)
                    if content == url:
                        read.assert_called_once_with(url, "")
                        self.assertEqual(report["newsletters"], snapshots)
                    notice, = report["notices"]
                    quote, = notice["evidence"]
                    source = text if content == url else content
                    self.assertEqual(quote["source"], field)
                    self.assertEqual(source[quote["start"]:quote["end"]], "bring hats")

    def test_parse_rejects_empty_or_unsupported_url_before_opening_model(self):
        with patch.object(GroqNoticeModel, "open") as open_model:
            for value in ("  ", "https://example.org/school"):
                with self.assertRaises(ValueError):
                    parse_notices(value)
            open_model.assert_not_called()

    def test_invalid_evidence_roster_and_structure(self):
        for change in ({"evidence": [dict(segment=2, quote="invented")]},
                       {"classes": ["Unknown"]}, {"review": "yes"},
                       {"audience_evidence": []}, {"whole_school": True}):
            with self.subTest(change=change), self.assertRaises(ValueError):
                self.result = {"notices": [dict(self.notice, **change)]}
                extract_notices(self.model, self.message)

    def test_oversized_newsletter_is_split_without_losing_text_or_offsets(self):
        text = "Oak hats.\nOak coats."
        self.responses = iter([
            httpx.Response(413, json={"error": {"message": "Request too large"}}),
            *({"notices": [dict(self.notice, evidence=[dict(segment=0, quote=word)],
                                audience_evidence=[dict(segment=0, quote="Oak")])]}
              for word in ("hats", "coats")),
        ])
        notices = extract_notices(self.model, replace(self.message, subject="", html="", text=""),
                                  newsletters={"newsletter_1": {"text": text}})
        halves = [json.loads(req["messages"][1]["content"])[0]["text"] for req in self.requests[1:]]
        self.assertEqual("".join(halves), text)
        self.assertEqual([n["audience_evidence"][0]["start"] for n in notices], [0, text.rindex("Oak")])
        for notice in notices:
            quote, = notice["evidence"]
            self.assertEqual(text[quote["start"]:quote["end"]], quote["quote"])

    def test_classified_export_reads_sway_once_and_preserves_newsletter_evidence(self):
        url = "https://sway.cloud.microsoft/SyntheticIssue"
        message = replace(self.message, html=f'<a href="{url}?ref=email">Weekly</a>',
                          text=f"{url}\nhttps://sway.cloud.microsoft.example.org/Other")
        viewer = ('var CommonSettings={"ClientDevice":"Desktop","UserSessionId":"session",'
                  '"AnonUserId":"anon","Canary":"synthetic"};var StoryPageSettings='
                  '{"ClientVersion":123,"StoryId":"story","LookupId":"SyntheticIssue"};')
        root = {"type": "Node-RenderModelRoot", "props": {"Title": "School news"}, "children": [
            {"type": "Node-TextRunElement", "props": {"Text": "Oak should bring hats."}},
        ]}
        requests = []

        def respond(request):
            requests.append(request)
            if request.method == "GET":
                self.assertEqual(str(request.url), url)
                return httpx.Response(200, text=viewer)
            self.assertEqual(request.url.path, "/s/SyntheticIssue/get")
            return httpx.Response(200, json={"StoryDiff": {"propBags": [root]}})

        self.notice.update(evidence=[dict(segment=2, quote="bring hats")],
                           audience_evidence=[dict(segment=2, quote="Oak")])
        client = httpx.Client(transport=httpx.MockTransport(respond))
        with tempfile.TemporaryDirectory() as tmp, patch("school_reminders.email.sway.httpx.Client",
                                                        return_value=client), redirect_stdout(StringIO()):
            output = Path(tmp) / "report.json"
            _export_messages([message], output, None)
            self.assertEqual(requests, [])
            _export_messages([message], output, self.model)
            row, = json.loads(output.read_text(encoding="utf-8"))
        self.assertEqual(len(requests), 2)
        quote, = row["notices"][0]["evidence"]
        snapshot = row["newsletters"][quote["source"]]
        self.assertEqual(snapshot["url"], url)
        self.assertEqual(snapshot["text"][quote["start"]:quote["end"]], "bring hats")
        payload = json.loads(self.requests[0]["messages"][1]["content"])
        self.assertEqual(payload[-1]["text"], "School news\nOak should bring hats.")
        self.assertNotIn("synthetic", str(payload).lower())

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

    def test_newsletter_can_cite_original_passages_after_failed_quote_correction(self):
        invalid = {"notices": [dict(self.notice, evidence=[dict(segment=0, quote="invented")])]}
        self.responses = iter([invalid, invalid, {"notices": [
            dict(self.notice, evidence=[1], audience_evidence=[0])
        ]}])
        text = "Oak\nBring hats."
        notice, = extract_notices(self.model, replace(self.message, subject="", html="", text=""),
                                  newsletters={"newsletter_1": {"text": text}})
        self.assertEqual(notice["evidence"], [
            dict(source="newsletter_1", start=4, end=len(text), quote="Bring hats.")
        ])

    def test_long_newsletter_selects_numbered_passages_directly(self):
        text = "Introduction. " * 300 + "\nOak should bring hats."
        self.responses = iter([{"notices": [dict(self.notice, evidence=[1], audience_evidence=[1])]}])
        notice, = extract_notices(self.model, replace(self.message, subject="", html="", text=""),
                                  newsletters={"newsletter_1": {"text": text}})
        request, = self.requests
        self.assertEqual(json.loads(request["messages"][1]["content"])[1],
                         [1, "newsletter_1", "Oak should bring hats."])
        self.assertEqual(notice["evidence"][0]["start"], text.index("Oak"))

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
