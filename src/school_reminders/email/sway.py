"""Read text from public Microsoft Sway newsletters linked in a school email."""

import json
import re
from collections.abc import Iterator
from html.parser import HTMLParser

import httpx

from school_reminders.domain.email_message import EmailMessage


_LINK = re.compile(
    r"https://(?:sway\.cloud\.microsoft|sway\.office\.com)/(?:s/)?([a-zA-Z0-9_-]+)"
    r"/?(?:[?#][^\s]*)?", re.IGNORECASE | re.ASCII,
)


class _Links(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.links: list[str] = []

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag == "a":
            self.links.extend(value for key, value in attrs if key == "href" and value)


def canonical_sway_url(candidate: str) -> str | None:
    match = _LINK.fullmatch(candidate.strip())
    return f"https://sway.cloud.microsoft/{match[1]}" if match else None


def _urls(text: str, html: str) -> list[str]:
    parser = _Links()
    parser.feed(html)
    parser.close()
    candidates = [*parser.links, *(url.rstrip(".,;:!") for url in
                  re.findall(r"""https://[^\s<>"'()\[\]]+""", text, re.IGNORECASE))]
    urls = {}
    for candidate in candidates:
        url = canonical_sway_url(candidate)
        if url:
            urls[url] = None
    return list(urls)


def _card_text(node: dict) -> Iterator[str]:
    props = node.get("props", {})
    kind = node.get("type")
    if kind == "Node-RenderModelRoot" and props.get("Title"):
        yield props["Title"]
    if kind == "Node-TextRunElement" and props.get("Text"):
        yield props["Text"]
    if kind == "Node-ImageLayoutElement":
        info = props.get("AccessibilityInfo", {})
        if isinstance(info, str):
            info = json.loads(info)
        for attr in info.get("Attributes", []):
            if attr["Name"].lower() in {"alt", "aria-label"} and attr.get("Value"):
                yield attr["Value"]
    for child in node.get("children", []):
        yield from _card_text(child)


def _settings(html: str, name: str) -> dict:
    marker = f"var {name}="
    _, found, rest = html.partition(marker)
    if not found:
        raise ValueError("Missing Sway viewer settings.")
    return json.JSONDecoder().raw_decode(rest.lstrip())[0]


def read_newsletters(message: EmailMessage) -> dict[str, dict[str, str]]:
    """Return ordered text snapshots for evidence offsets, keyed by model source label."""
    return newsletters_from_content(message.text, message.html)


def newsletters_from_content(text: str, html: str) -> dict[str, dict[str, str]]:
    """Read public Sways referenced in a body or supplied as a standalone link."""
    snapshots = {}
    for url in _urls(text, html):
        try:
            with httpx.Client(timeout=45) as client:
                page = client.get(url)
                page.raise_for_status()
                story = _settings(page.text, "StoryPageSettings")
                common = _settings(page.text, "CommonSettings")
                version = str(story["ClientVersion"])
                response = client.post(
                    url.replace(".microsoft/", ".microsoft/s/") + "/get",
                    params={"currentClientVersion": version},
                    headers={"X-StoryId": story["StoryId"], "X-LookupId": story["LookupId"],
                             "X-WebClientVersion": version, "X-UserSessionId": common["UserSessionId"],
                             "anonuserid": common["AnonUserId"], "X-Key": common["Canary"]},
                    data={"clientDevice": common["ClientDevice"], "width": "1280", "height": "900",
                          "isAccessibleMode": "true", "countView": "false", "viewOptionOverrides": "{}"},
                )
                response.raise_for_status()
                roots = response.json()["StoryDiff"]["propBags"]
                text = "\n".join(line for root in roots for line in _card_text(root))
                if not text.strip():
                    raise ValueError("Empty newsletter.")
        except (httpx.HTTPError, KeyError, ValueError, TypeError, AttributeError, RecursionError) as error:
            raise ValueError("Could not read a linked Microsoft Sway newsletter.") from error
        snapshots[f"newsletter_{len(snapshots) + 1}"] = {"url": url, "text": text}
    return snapshots
