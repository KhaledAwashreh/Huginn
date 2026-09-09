from __future__ import annotations

from huginn.silver.resolution import MatchConfidence
from huginn.silver.signal_resolution import (
    _NON_COMPANY_HOSTS,
    resolve_signal,
    unresolved_placeholder_key,
)


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


def test_resolve_signal_rejects_a_denylisted_ats_host():
    key, confidence = resolve_signal(
        "hn", "1", "https://acme.bamboohr.com/jobs/view/42"
    )

    assert key == "unresolved:hn:1"
    assert confidence == MatchConfidence.NO_EXISTING_MATCH


def test_resolve_signal_rejects_a_denylisted_platform_host():
    key, confidence = resolve_signal("yc", "7", "https://www.ycombinator.com/companies")

    assert key == "unresolved:yc:7"
    assert confidence == MatchConfidence.NO_EXISTING_MATCH


def test_resolve_signal_rejects_a_subdomain_of_a_denylisted_host():
    key, confidence = resolve_signal("hn", "2", "https://boards.greenhouse.io/acme")

    assert key == "unresolved:hn:2"
    assert confidence == MatchConfidence.NO_EXISTING_MATCH


def test_resolve_signal_rejects_every_denylisted_host():
    for host in _NON_COMPANY_HOSTS:
        key, confidence = resolve_signal("hn", "1", f"https://{host}/careers")

        assert confidence == MatchConfidence.NO_EXISTING_MATCH, host
        assert key == "unresolved:hn:1", host


def test_resolve_signal_still_auto_matches_a_real_company_domain():
    """Regression check for the denylist: a company domain that merely
    resembles a denylisted one, or contains it as a non-suffix substring,
    must still auto-match.
    """
    for website in (
        "https://modash.io",
        "https://www.acme.com/careers",
        "https://notgreenhouse.io",
        "https://greenhouse.io.acme.com",
        "https://careers.acme.com",
    ):
        _, confidence = resolve_signal("hn", "1", website)

        assert confidence == MatchConfidence.AUTO_MATCHED, website


def test_unresolved_placeholder_key_is_scoped_by_source_and_stable_id():
    assert unresolved_placeholder_key("hn", "1") != unresolved_placeholder_key(
        "yc", "1"
    )
    assert unresolved_placeholder_key("hn", "1") != unresolved_placeholder_key(
        "hn", "2"
    )
