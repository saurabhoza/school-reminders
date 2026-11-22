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
            '<head><title>hidden</title></head><p>Oak</p><p>On 12 May bring hats &amp; coats.</p>'
            '<a href="https://example.org/private">All classes finish early on 13 May.</a>', "text/html",
        ))
        self.notice = dict(date_evidence=dict(segment=2, quote="12 May"), title="Bring outdoor clothes", years=[], classes=["Oak"],
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
        self.result["notices"].append(dict(self.notice, title="Early finish", date_evidence=dict(segment=3, quote="13 May"), classes=[],
            whole_school=True, evidence=[dict(segment=3, quote="All classes finish early on 13 May.")],
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
                         ["Year 4 trip", "Oak", "On 12 May bring hats &amp; coats.", "All classes finish early on 13 May."])
        self.assertTrue(request["response_format"]["json_schema"]["strict"])

    def test_retries_groq_output_validation_error_once(self):
        def rejected():
            return httpx.Response(400, json={"error": {"code": "json_validate_failed",
                                                       "failed_generation": "private content"}})

        self.responses = iter([rejected(), self.result])
        notice, = extract_notices(self.model, self.message)
        self.assertEqual(notice["event_date"], "12 May")
        self.assertEqual(len(self.requests), 2)
        self.responses = iter([rejected(), rejected()])
        with self.assertRaisesRegex(ValueError, "code=json_validate_failed"):
            extract_notices(self.model, self.message)
        self.assertEqual(len(self.requests), 4)

    def test_other_bad_requests_report_code_without_echoing_private_data(self):
        self.responses = iter([httpx.Response(400, headers={"x-request-id": "req_test"},
            json={"error": {"code": "invalid_parameter", "message": "private content"}})])
        with self.assertRaises(ValueError) as caught:
            extract_notices(self.model, self.message)
        self.assertIn("invalid_parameter", str(caught.exception))
        self.assertIn("req_test", str(caught.exception))
        self.assertNotIn("private content", str(caught.exception))
        self.assertEqual(len(self.requests), 1)

    def test_parse_pasted_email_and_standalone_sway(self):
        text = "  Oak should bring hats on 12 May."
        url = "https://sway.cloud.microsoft/SyntheticIssue"
        snapshots = {"newsletter_1": {"url": url, "text": text}}
        with patch.object(GroqNoticeModel, "open") as open_model:
            open_model.return_value.__enter__.return_value = self.model
            for content, options, field, index in [
                (text, {"subject": "Class trip"}, "text", 1),
                (f"<p>{text}</p>", {"html": True}, "html", 0),
                (url, {}, "newsletter_1", 0),
            ]:
                self.notice.update(date_evidence=dict(segment=index, quote="12 May"), evidence=[dict(segment=index, quote="bring hats")],
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
        text = "Oak hats 12 May.\nOak coats 13 May."
        self.responses = iter([
            httpx.Response(413, json={"error": {"message": "Request too large"}}),
            *({"notices": [dict(self.notice, date_evidence=dict(segment=0, quote=day), evidence=[dict(segment=0, quote=word)],
                                audience_evidence=[dict(segment=0, quote="Oak")])]}
              for word, day in (("hats", "12 May"), ("coats", "13 May"))),
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
            {"type": "Node-TextRunElement", "props": {"Text": "Oak should bring hats on 12 May."}},
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
        self.assertEqual(payload[-1]["text"], "School news\nOak should bring hats on 12 May.")
        self.assertNotIn("synthetic", str(payload).lower())

    def test_ambiguous_and_empty_results(self):
        self.notice.update(classes=[], audience_evidence=[])
        self.assertTrue(extract_notices(self.model, self.message)[0]["audience"]["review"])
        self.result = {"notices": []}
        self.assertEqual(extract_notices(self.model, self.message), [])

    def test_skips_undated_requests_and_repeated_event(self):
        for date_quote in (None, "as soon as possible", "31 February"):
            unsupported = dict(self.notice, title="Return borrowed books",
                               date_evidence=dict(segment=0, quote=date_quote) if date_quote else None)
            self.result = {"notices": [unsupported, self.notice, self.notice]}
            with self.subTest(date_quote=date_quote):
                event, = extract_notices(self.model, self.message)
                self.assertEqual(event["event_date"], "12 May")
                self.assertEqual(event["title"], "Bring outdoor clothes")

    def test_cannot_use_email_receipt_date_as_event_evidence(self):
        self.notice["date_evidence"] = dict(segment=2, quote="14 June")
        with self.assertRaisesRegex(ValueError, "absent from its source"):
            extract_notices(self.model, replace(self.message, date="14 June"))

    def test_dated_optional_days_survive_long_newsletter_validation(self):
        dates = ["Monday 16th November", "Friday 20th November"]
        titles = ["Pattern Day", "Colour Day"]
        lines = [f"{day} - {title} - All pupils may dress up." for day, title in zip(dates, titles)]
        text = "Introduction. " * 300 + "\n" + "\n".join(lines)
        self.result = {"notices": [
            dict(self.notice, title=title, date_evidence=dict(segment=i, quote=day),
                 evidence=[i], whole_school=True, classes=[],
                 audience_evidence=[dict(segment=i, quote="All pupils")])
            for i, (day, title) in enumerate(zip(dates, titles), 1)
        ]}
        entries = extract_notices(self.model, replace(self.message, subject="", html="", text=""),
                                  newsletters={"newsletter_1": {"text": text}})
        self.assertEqual([n["event_date"] for n in entries], dates)
        for entry in entries:
            citation = entry["date_evidence"]
            self.assertEqual(text[citation["start"]:citation["end"]], entry["event_date"])
        # Sway renders the heading, dash, and invitation as separate text runs.
        split_lines = text.replace(" - All pupils may dress up.", "\n- \nAll pupils may wear stripes.")
        self.result = {"notices": []}
        recovered = extract_notices(self.model, replace(self.message, subject="", html="", text=""),
                                    newsletters={"newsletter_1": {"text": split_lines}})
        self.assertEqual([n["title"] for n in recovered], titles)
        for entry in recovered:
            self.assertTrue(entry["audience"]["whole_school"])
            self.assertEqual(entry["audience_evidence"][0]["quote"], "All pupils")

    def test_compacts_excess_citations_after_verification(self):
        self.notice["audience_evidence"] *= 12
        self.notice["evidence"] = [dict(segment=2, quote=q) for q in ("hats", "hats", "coats", "12 May")]
        event, = extract_notices(self.model, self.message)
        self.assertEqual([c["quote"] for c in event["evidence"]], ["hats", "coats"])
        self.assertEqual([c["quote"] for c in event["audience_evidence"]], ["Oak"])
        self.assertEqual(len(self.requests), 1)
        self.notice["evidence"].append(dict(segment=2, quote="invented"))
        with self.assertRaisesRegex(ValueError, "absent from its source"):
            extract_notices(self.model, self.message)

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
            dict(self.notice, date_evidence=dict(segment=1, quote="12 May"), evidence=[1], audience_evidence=[dict(segment=0, quote="Oak")])
        ]}])
        text = "Oak\nBring hats on 12 May."
        notice, = extract_notices(self.model, replace(self.message, subject="", html="", text=""),
                                  newsletters={"newsletter_1": {"text": text}})
        self.assertEqual(notice["evidence"], [
            dict(source="newsletter_1", start=4, end=len(text), quote="Bring hats on 12 May.")
        ])

    def test_long_newsletter_selects_numbered_passages_directly(self):
        text = "Introduction. " * 300 + "\nOak should bring hats on 12 May."
        self.responses = iter([{"notices": [dict(self.notice, date_evidence=dict(segment=1, quote="12 May"), evidence=[1], audience_evidence=[dict(segment=1, quote="Oak")])]}])
        notice, = extract_notices(self.model, replace(self.message, subject="", html="", text=""),
                                  newsletters={"newsletter_1": {"text": text}})
        request, = self.requests
        self.assertEqual(json.loads(request["messages"][1]["content"])[1],
                         [1, "newsletter_1", "Oak should bring hats on 12 May."])
        self.assertEqual(notice["evidence"][0]["start"], text.index("Oak"))

    def test_rejects_repeatedly_unsupported_audience(self):
        self.notice["audience_evidence"] = []
        with self.assertRaisesRegex(ValueError, "without evidence"):
            extract_notices(self.model, self.message)
        self.assertEqual(len(self.requests), 2)

    def test_long_sway_keeps_verified_events_with_missing_audience_evidence(self):
        url = "https://sway.cloud.microsoft/SyntheticIssue"
        text = "Introduction. " * 300 + "\nMuseum trip on 12 May.\nOak concert on 13 May."
        trip = dict(self.notice, title="Museum trip", date_evidence=dict(segment=1, quote="12 May"),
                    evidence=[1], classes=[], whole_school=True, audience_evidence=[])
        concert = dict(self.notice, title="Concert", date_evidence=dict(segment=2, quote="13 May"),
                       evidence=[2], audience_evidence=[dict(segment=2, quote="Oak")])
        self.result = {"notices": [trip, concert]}
        with patch.object(GroqNoticeModel, "open") as opened, patch(
            "school_reminders.extraction.newsletters_from_content",
            return_value={"newsletter_1": {"url": url, "text": text}},
        ):
            opened.return_value.__enter__.return_value = self.model
            unknown, confirmed = parse_notices(url)["notices"]
            self.assertEqual(unknown["audience"], dict(years=[], classes=[], whole_school=False,
                                                       class_years={}, review=True))
            self.assertEqual(unknown["audience_evidence"], [])
            self.assertEqual(unknown["evidence"][0]["quote"], "Museum trip on 12 May.")
            self.assertEqual(confirmed["audience"]["class_years"], {"Oak": "Year 4"})
            self.assertEqual(len(self.requests), 1)
            trip["date_evidence"]["quote"] = "14 May"
            with self.assertRaisesRegex(ValueError, "absent from its source"):
                parse_notices(url)

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
            display.assert_any_call("  - 12 May — Bring outdoor clothes | Oak (Year 4)")
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
