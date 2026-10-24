"""Pure normalization of collected Hacker News item payloads."""

from __future__ import annotations

import re
from typing import cast

from bs4 import BeautifulSoup

from huginn.elt.silver.models.source_extraction import SourceExtraction
from huginn.elt.silver.types.source_context import OutcomeStatus

_HN_ITEM_URL = "https://news.ycombinator.com/item?id={id}"
_PARAGRAPH_RE = re.compile(r"<p(?:\s[^>]*)?>", re.IGNORECASE)
_BLOCK_TAGS = (
    "address",
    "article",
    "blockquote",
    "br",
    "dd",
    "div",
    "dl",
    "dt",
    "h1",
    "h2",
    "h3",
    "h4",
    "h5",
    "h6",
    "li",
    "ol",
    "p",
    "pre",
    "section",
    "tr",
    "ul",
)


def _stable_id(payload: dict[str, object]) -> str | None:
    value = payload.get("id")
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        return None
    stable_id = str(value).strip()
    return stable_id or None


def _valid_source_time(payload: dict[str, object]) -> bool:
    if "time" not in payload:
        return True
    value = payload["time"]
    return isinstance(value, int) and not isinstance(value, bool)


def _visible_text(fragment: str) -> str:
    soup = BeautifulSoup(fragment, "html.parser")
    for tag in soup(("script", "style")):
        tag.decompose()
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    raw = soup.get_text()
    lines = [re.sub(r"\s+", " ", line).strip() for line in raw.splitlines()]
    return "\n".join(line for line in lines if line)


def _links(fragment: str) -> list[dict[str, str]]:
    soup = BeautifulSoup(fragment, "html.parser")
    links: list[dict[str, str]] = []
    for anchor in soup.find_all("a", href=True):
        links.append(
            {
                "anchor_text": " ".join(anchor.get_text(" ", strip=True).split()),
                "href": cast(str, anchor["href"]),
            }
        )
    return links


def _outcome(
    *,
    stable_id: str | None,
    status: OutcomeStatus,
    reason: str,
    payload: dict[str, object] | None = None,
) -> SourceExtraction:
    return SourceExtraction(
        source="hn",
        stable_id=stable_id,
        status=status,
        reason=reason,
        source_url=_HN_ITEM_URL.format(id=stable_id) if stable_id is not None else None,
        source_times={"time": payload["time"]}
        if payload is not None and "time" in payload
        else {},
    )


def normalize_hn(payload: dict[str, object]) -> SourceExtraction:
    """Normalize one stored HN payload without fetching or resolving anything.

    Exclusion precedence is root item, deleted item, dead item, then empty
    text. Structural/type errors are failed outcomes; unsupported item types
    are excluded as non-comments.
    """
    if not isinstance(payload, dict):
        return _outcome(stable_id=None, status="failed", reason="malformed_payload")

    stable_id = _stable_id(payload)
    if not _valid_source_time(payload):
        return _outcome(
            stable_id=stable_id,
            status="failed",
            reason="malformed_source_time",
        )
    item_type = payload.get("type")
    if item_type == "story":
        return _outcome(
            stable_id=stable_id, status="excluded", reason="root_item", payload=payload
        )
    if payload.get("deleted") is True:
        return _outcome(
            stable_id=stable_id,
            status="excluded",
            reason="deleted_item",
            payload=payload,
        )
    if payload.get("dead") is True:
        return _outcome(
            stable_id=stable_id, status="excluded", reason="dead_item", payload=payload
        )
    if item_type != "comment":
        if isinstance(item_type, str):
            return _outcome(
                stable_id=stable_id,
                status="excluded",
                reason="non_comment",
                payload=payload,
            )
        return _outcome(
            stable_id=stable_id,
            status="failed",
            reason="malformed_payload",
            payload=payload,
        )

    for flag in ("deleted", "dead"):
        if flag in payload and not isinstance(payload[flag], bool):
            return _outcome(
                stable_id=stable_id,
                status="failed",
                reason="malformed_payload",
                payload=payload,
            )

    raw_text = payload.get("text")
    if raw_text is None or raw_text == "":
        return _outcome(
            stable_id=stable_id,
            status="excluded",
            reason="empty_text",
            payload=payload,
        )
    if not isinstance(raw_text, str):
        return _outcome(
            stable_id=stable_id,
            status="failed",
            reason="malformed_payload",
            payload=payload,
        )
    if stable_id is None:
        return _outcome(
            stable_id=None,
            status="failed",
            reason="malformed_payload",
            payload=payload,
        )

    paragraph = _PARAGRAPH_RE.search(raw_text)
    links = _links(raw_text)
    if paragraph is None:
        normalized_text = _visible_text(raw_text)
        header_span = None
        body_span = None
    else:
        header = _visible_text(raw_text[: paragraph.start()])
        body = _visible_text(raw_text[paragraph.end() :])
        normalized_text = f"{header}\n{body}" if header and body else header or body
        if header and body:
            header_span = (0, len(header))
            body_span = (len(header) + 1, len(normalized_text))
        elif header:
            header_span = (0, len(header))
            body_span = (len(header), len(header))
        else:
            header_span = (0, 0)
            body_span = (0, len(body))

    if not normalized_text:
        return _outcome(
            stable_id=stable_id,
            status="excluded",
            reason="empty_text",
            payload=payload,
        )

    source_times = {"time": payload["time"]} if "time" in payload else {}
    return SourceExtraction(
        source="hn",
        stable_id=stable_id,
        status="captured",
        source_url=_HN_ITEM_URL.format(id=stable_id),
        normalized_text=normalized_text,
        header_span=header_span,
        body_span=body_span,
        source_fields={"item_type": "comment", "links": links},
        source_times=source_times,
    )
