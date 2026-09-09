from __future__ import annotations

from huginn.silver.resolution import MatchConfidence
from huginn.silver.signal_resolution import resolve_signal, unresolved_placeholder_key


def test_resolve_signal_auto_matches_a_normalizable_domain():
    key, confidence = resolve_signal("hn", "1", "https://www.acme.com/careers")

    assert key == "acme.com"
    assert confidence == MatchConfidence.AUTO_MATCHED


def test_resolve_signal_returns_no_existing_match_when_website_is_none():
    key, confidence = resolve_signal("hn", "1", None)

    assert key == "unresolved:hn:1"
    assert confidence == MatchConfidence.NO_EXISTING_MATCH


def test_resolve_signal_returns_no_existing_match_when_website_is_empty_string():
    key, confidence = resolve_signal("hn", "1", "")

    assert key == "unresolved:hn:1"
    assert confidence == MatchConfidence.NO_EXISTING_MATCH


def test_unresolved_placeholder_key_is_scoped_by_source_and_stable_id():
    assert unresolved_placeholder_key("hn", "1") != unresolved_placeholder_key(
        "yc", "1"
    )
    assert unresolved_placeholder_key("hn", "1") != unresolved_placeholder_key(
        "hn", "2"
    )
