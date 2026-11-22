"""Prepare ordered email text segments with offsets into the decoded source."""

import re
from dataclasses import dataclass
from html.parser import HTMLParser

from school_reminders.domain.email_message import EmailMessage


@dataclass(frozen=True)
class Segment:
    source: str
    start: int
    text: str


class _HTMLSegments(HTMLParser):
    """Keep visible text nodes and original entity spelling for exact quotations."""

    def __init__(self, html: str) -> None:
        super().__init__(convert_charrefs=False)
        self.html = html
        self.lines = [0, *(m.end() for m in re.finditer("\n", html))]
        self.segments: list[Segment] = []
        self.hidden = 0

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag in {"head", "script", "style"}:
            self.hidden += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in {"head", "script", "style"}:
            self.hidden = max(0, self.hidden - 1)

    def _offset(self) -> int:
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_data(self, data: str) -> None:
        if self.hidden or not data:
            return
        start = self._offset()
        if self.segments:
            last = self.segments[-1]
            if last.start + len(last.text) == start:
                self.segments[-1] = Segment("html", last.start, last.text + data)
                return
        self.segments.append(Segment("html", start, data))

    def handle_entityref(self, name: str) -> None:
        start = self._offset()
        end = start + len(name) + 1
        if self.html.startswith(";", end):
            end += 1
        self.handle_data(self.html[start:end])

    def handle_charref(self, name: str) -> None:
        self.handle_entityref("#" + name)


def source_segments(message: EmailMessage) -> list[Segment]:
    """Use original HTML when present, since message.text can be HTML-derived."""
    return content_segments(message.subject, message.text, message.html)


def content_segments(subject: str, text: str, html: str) -> list[Segment]:
    """Build evidence segments from a decoded subject and body."""
    parts = [Segment("subject", 0, subject)]
    if html:
        parser = _HTMLSegments(html)
        parser.feed(html)
        parser.close()
        parts.extend(parser.segments)
    else:
        parts.append(Segment("text", 0, text))
    return [part for part in parts if part.text.strip()]
