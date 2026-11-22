"""Extract notices and verify their audiences and quotes against the local source."""

import re
from collections.abc import Iterator
from datetime import datetime

from school_reminders.domain.audience import CLASS_YEARS, ROSTER
from school_reminders.domain.email_message import EmailMessage
from school_reminders.email.notices import Segment, content_segments, source_segments
from school_reminders.email.sway import canonical_sway_url, newsletters_from_content, read_newsletters
from school_reminders.groq_model import Citation, GroqNoticeModel, Notice, RequestTooLarge


class EvidenceError(ValueError):
    """A model citation failed local verification."""


def _verify(citation: Citation, segments: list[Segment]) -> dict:
    if not 0 <= citation.segment < len(segments) or not citation.quote.strip():
        raise EvidenceError("Groq returned an invalid evidence reference.")
    part = segments[citation.segment]
    offset = part.text.find(citation.quote)
    if offset < 0:
        raise EvidenceError("Groq returned a quote absent from its source.")
    start = part.start + offset
    return dict(source=part.source, start=start, end=start + len(citation.quote), quote=citation.quote)


def _calendar_date(text: str) -> bool:
    """Accept a calendar day and month; validate yearless dates against a leap year."""
    text = re.sub(
        r"^(?:Mon(?:day)?|Tue(?:sday)?|Wed(?:nesday)?|Thu(?:rsday)?|Fri(?:day)?|Sat(?:urday)?|Sun(?:day)?)"
        r"\.?\s*,?\s+", "", text.strip(), flags=re.I,
    )
    text = re.sub(r"(?<=\d)(?:st|nd|rd|th)\b", "", text.strip(), flags=re.I)
    text = re.sub(r"\bSept\b", "Sep", text, flags=re.I)
    text = " ".join(text.replace(",", " ").split())
    numeric = text.replace(".", "/").replace("-", "/")
    for value, formats in (
        (numeric, ("%Y/%m/%d", "%d/%m/%Y", "%d/%m/%y")),
        (numeric + "/2000", ("%d/%m/%Y",)),
        (text, ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y")),
        (text + " 2000", ("%d %B %Y", "%d %b %Y", "%B %d %Y", "%b %d %Y")),
    ):
        for fmt in formats:
            try:
                datetime.strptime(value, fmt)
            except ValueError:
                continue
            return True
    return False


def _validated_notice(notice: Notice, segments: list[Segment]) -> dict | None:
    if notice.date_evidence is None or not _calendar_date(notice.date_evidence.quote):
        return None
    date_evidence = _verify(notice.date_evidence, segments)
    if not notice.title.strip() or not notice.evidence:
        raise ValueError("Groq returned a notice without a title or evidence.")
    if set(notice.years).difference(ROSTER) or set(notice.classes).difference(CLASS_YEARS):
        raise ValueError("Groq returned an unknown year or class.")
    if notice.whole_school and (notice.years or notice.classes):
        raise EvidenceError("Groq returned conflicting audiences. Whole-school events must have empty class and year lists.")
    assigned = bool(notice.whole_school or notice.years or notice.classes)
    if assigned and not notice.audience_evidence:
        raise EvidenceError("Groq assigned an audience without evidence.")
    if any(len(item.quote) > 100 for item in notice.audience_evidence):
        raise EvidenceError("Quote only the audience phrase (100 characters maximum).")
    return {
        "title": notice.title,
        "event_date": date_evidence["quote"],
        "date_evidence": date_evidence,
        "audience": {
            "years": notice.years, "classes": notice.classes, "whole_school": notice.whole_school,
            "class_years": {name: CLASS_YEARS[name] for name in notice.classes},
            "review": notice.review or not assigned,
        },
        "evidence": _concise_evidence(notice.evidence, segments),
        "audience_evidence": _concise_evidence(notice.audience_evidence, segments),
    }


def _concise_evidence(citations: list[Citation], segments: list[Segment]) -> list[dict]:
    """Verify every citation and keep the first two distinct source spans for display."""
    result = []
    for item in citations:
        verified = _verify(item, segments)
        if len(result) < 2 and verified not in result:
            result.append(verified)
    return result


def extract_notices(model: GroqNoticeModel, message: EmailMessage, *,
                    newsletters: dict[str, dict[str, str]] | None = None) -> list[dict]:
    """Extract one report per nonempty message, then verify it before export."""
    segments = source_segments(message)
    if newsletters is None:
        newsletters = read_newsletters(message)
    return _identify(model, segments, newsletters)


def parse_notices(content: str, *, subject: str = "", html: bool = False) -> dict:
    """Classify a pasted body or public Sway URL and return notices and cited newsletter snapshots.

    Set html=True for an HTML email body. Email quote offsets refer to the original
    input or subject. Newsletter offsets refer to the returned snapshot's text.
    """
    if not content.strip():
        raise ValueError("Provide email content or a public Microsoft Sway URL.")
    text, markup = ("", content) if html else (content, "")
    url_only = not html and re.fullmatch(r"https?://\S+", text.strip(), re.IGNORECASE) is not None
    if url_only:
        url = canonical_sway_url(text)
        if url is None:
            raise ValueError("Provide a direct public Microsoft Sway URL.")
        text = url
    with GroqNoticeModel.open() as model:
        newsletters = newsletters_from_content(text, markup)
        segments = content_segments(subject, "" if url_only else text, markup)
        notices = _identify(model, segments, newsletters)
    return {"notices": notices, "newsletters": newsletters}


def _identify(model: GroqNoticeModel, segments: list[Segment],
              newsletters: dict[str, dict[str, str]]) -> list[dict]:
    for label, snapshot in newsletters.items():
        text = snapshot["text"]
        start = 0
        # Group adjacent lines so the model can reference a short numbered passage.
        for match in re.finditer(r"\n|\Z", text):
            end = match.end()
            if end - start >= 500 or end == len(text):
                if text[start:end].strip():
                    segments.append(Segment(label, start, text[start:end]))
                start = end
    if not segments:
        return []
    results = []
    for notice in _identify_batch(model, segments):
        if notice not in results:
            results.append(notice)
    for label, snapshot in newsletters.items():
        for event in _participation_days(label, snapshot["text"]):
            heading = event["evidence"][0]
            if not any(
                n["date_evidence"]["source"] == label
                and heading["start"] <= n["date_evidence"]["start"] < heading["end"]
                for n in results
            ):
                results.append(event)
    return results


def _participation_days(source: str, text: str) -> Iterator[dict]:
    """Recover explicit date–title headings immediately followed by a school-wide invitation."""
    headings = re.finditer(
        r"^[ \t]*(?P<date>(?:(?:Monday|Tuesday|Wednesday|Thursday|Friday|Saturday|Sunday),?\s+)?"
        r"\d{1,2}(?:st|nd|rd|th)?[ \t]+[A-Za-z]+(?:[ \t]+\d{4})?)[ \t]*[-–—][ \t]*"
        r"(?P<title>[^\r\n]{1,100}?\bDay)\b[ \t-]*(?:\r?\n[ \t-]*)*"
        r"(?P<audience>All (?:adults and children|children and adults|pupils|children)"
        r"(?: in school)?)(?:\s*\(and\s+home!\))?\s+(?:are invited to|can wear|may wear)\b",
        text, re.I | re.M,
    )
    for match in headings:
        if not _calendar_date(match["date"]):
            continue
        def citation(start: int, end: int) -> dict:
            return dict(source=source, start=start, end=end, quote=text[start:end])

        yield {
            "title": match["title"], "event_date": match["date"],
            "date_evidence": citation(*match.span("date")),
            "audience": dict(years=[], classes=[], whole_school=True, class_years={}, review=False),
            "evidence": [citation(match.start("date"), match.end("title"))],
            "audience_evidence": [citation(*match.span("audience"))],
        }


def _identify_batch(model: GroqNoticeModel, segments: list[Segment]) -> list[dict]:
    try:
        return _verified_report(model, segments)
    except RequestTooLarge:
        if len(segments) > 1:
            mid = len(segments) // 2
            left, right = segments[:mid], segments[mid:]
        else:
            part, = segments
            if len(part.text) < 2:
                raise
            mid = len(part.text) // 2
            # Prefer a nearby line boundary, then whitespace, before splitting a word.
            for delimiter in ("\n", " "):
                boundary = part.text.rfind(delimiter, mid // 2, mid)
                if boundary >= 0:
                    mid = boundary + 1
                    break
            left = [Segment(part.source, part.start, part.text[:mid])]
            right = [Segment(part.source, part.start + mid, part.text[mid:])]
    return _identify_batch(model, left) + _identify_batch(model, right)


def _verified_report(model: GroqNoticeModel, segments: list[Segment]) -> list[dict]:
    has_newsletter = any(part.source.startswith("newsletter_") for part in segments)
    if has_newsletter and sum(len(part.text) for part in segments) > 4000:
        # Index-only citations keep long newsletters' responses small.
        return _select_evidence(model, segments)
    report = model.identify(segments)
    try:
        return [entry for notice in report.notices if (entry := _validated_notice(notice, segments))]
    except EvidenceError as error:
        report = model.identify(segments, correction=str(error))
    try:
        return [entry for notice in report.notices if (entry := _validated_notice(notice, segments))]
    except EvidenceError:
        if not has_newsletter:
            raise
    return _select_evidence(model, segments)


def _select_evidence(model: GroqNoticeModel, segments: list[Segment]) -> list[dict]:
    passages = []
    for part in segments:
        for line in re.finditer(r"[^\r\n]+", part.text):
            if line[0].strip():
                passages.append(Segment(part.source, part.start + line.start(), line[0]))

    def citation(index: int) -> Citation:
        if not 0 <= index < len(passages):
            raise EvidenceError("Groq selected an unknown evidence passage.")
        return Citation(segment=index, quote=passages[index].text)

    notices = []
    for selected in model.select_passages(passages).notices:
        values = selected.model_dump(exclude={"evidence"})
        # This is the final newsletter extraction path. A missing audience citation
        # leaves the recipients unknown; the event and date still need verification.
        try:
            for item in selected.audience_evidence:
                _verify(item, passages)
        except EvidenceError:
            values["audience_evidence"] = []
        if not values["audience_evidence"]:
            values.update(years=[], classes=[], whole_school=False, review=True)
        notice = Notice(**values, evidence=[citation(i) for i in selected.evidence])
        entry = _validated_notice(notice, passages)
        if entry:
            notices.append(entry)
    return notices
