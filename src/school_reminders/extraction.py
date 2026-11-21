"""Extract notices and verify their audiences and quotes against the local source."""

from school_reminders.domain.audience import CLASS_YEARS, ROSTER
from school_reminders.domain.email_message import EmailMessage
from school_reminders.email.notices import Segment, source_segments
from school_reminders.groq_model import Citation, GroqNoticeModel, Notice


def _verify(citation: Citation, segments: list[Segment]) -> dict:
    if not 0 <= citation.segment < len(segments) or not citation.quote.strip():
        raise ValueError("Groq returned an invalid evidence reference.")
    part = segments[citation.segment]
    offset = part.text.find(citation.quote)
    if offset < 0:
        raise ValueError("Groq returned a quote absent from its source.")
    start = part.start + offset
    return dict(source=part.source, start=start, end=start + len(citation.quote), quote=citation.quote)


def _validated_notice(notice: Notice, segments: list[Segment]) -> dict:
    if not notice.title.strip() or not notice.evidence:
        raise ValueError("Groq returned a notice without a title or evidence.")
    if set(notice.years).difference(ROSTER) or set(notice.classes).difference(CLASS_YEARS):
        raise ValueError("Groq returned an unknown year or class.")
    if notice.whole_school and (notice.years or notice.classes):
        raise ValueError("Groq returned conflicting audiences.")
    assigned = bool(notice.whole_school or notice.years or notice.classes)
    if assigned and not notice.audience_evidence:
        raise ValueError("Groq assigned an audience without evidence.")
    return {
        "title": notice.title,
        "audience": {
            "years": notice.years, "classes": notice.classes, "whole_school": notice.whole_school,
            "class_years": {name: CLASS_YEARS[name] for name in notice.classes},
            "review": notice.review or not assigned,
        },
        "evidence": [_verify(item, segments) for item in notice.evidence],
        "audience_evidence": [_verify(item, segments) for item in notice.audience_evidence],
    }


def extract_notices(model: GroqNoticeModel, message: EmailMessage) -> list[dict]:
    """Extract one report per nonempty message, then verify it before export."""
    segments = source_segments(message)
    if not segments:
        return []
    report = model.identify(segments)
    return [_validated_notice(notice, segments) for notice in report.notices]
