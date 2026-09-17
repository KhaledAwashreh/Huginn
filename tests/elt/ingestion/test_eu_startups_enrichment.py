from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests

from huginn.elt.ingestion.adapters import eu_startups_enrichment
from huginn.elt.ingestion.adapters.eu_startups_enrichment import (
    EuStartupsEnrichmentAdapter,
    EuStartupsEnrichmentFetchError,
    _build_search_url,
    _extract_exact_matches,
    _extract_raw_matches,
    _is_result_set_truncated,
    _parsed_result_count,
)
from huginn.elt.ingestion.ports import WebScrapeSourcePort

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "eu_startups"

# No live query produced a ">1 exact match" page; a small, hand-written
# fragment reusing the real `.search-results .listing-title a` structure
# (plan Global Constraint 11, same pattern as
# `test_eu_startups_staging.py`'s field-free fragment). The `<h3>Search
# Results (2)</h3>` header matches the 2 anchors below so the Fix 1
# truncation guard doesn't intercept this fixture before the exact-match
# tests it's meant for ever run.
_TWO_EXACT_MATCHES_HTML = """
<h3>Search Results (2)</h3>
<div class="search-results">
  <div class="listing-title"><a href="https://www.eu-startups.com/directory/dupeco/">DupeCo</a></div>
  <div class="listing-title"><a href="https://www.eu-startups.com/directory/dupeco-2/">DupeCo</a></div>
</div>
"""

# Same shape, header mismatched with the raw anchor count on purpose: the
# standard "hand-written minimal HTML for an edge case no real page shows"
# pattern, this time for the Fix 1 truncation guard itself.
_TRUNCATED_SEARCH_RESULTS_HTML = """
<h3>Search Results (5)</h3>
<div class="search-results">
  <div class="listing-title"><a href="https://www.eu-startups.com/directory/truncateco/">TruncateCo</a></div>
  <div class="listing-title"><a href="https://www.eu-startups.com/directory/other-co/">Other Co</a></div>
</div>
"""


def _read_fixture(name: str) -> str:
    return (_FIXTURES / name).read_text()


def _fake_fetch_page(url: str, search_html: str, detail_html: str) -> str:
    """Route a monkeypatched `fetch_page` call by URL shape: the directory
    search URL (`?dosrch=1`) gets the preloaded search-results fixture,
    everything else (a listing detail page) gets the preloaded detail
    fixture. Mirrors `test_eu_startups.py`'s `_fake_fetch_page` routing
    style.
    """
    if "dosrch=1" in url:
        return search_html
    return detail_html


def test_extract_exact_matches_returns_the_single_case_matching_result():
    matches = _extract_exact_matches(
        _read_fixture("search_brightroom.html"), "Brightroom"
    )

    assert matches == [
        ("Brightroom", "https://www.eu-startups.com/directory/brightroom/")
    ]


def test_extract_exact_matches_is_case_insensitive():
    """Real fixture: querying "Varm" resolves to a result displayed as
    "VARM". The filter must still keep it (plan Global Constraint 8)."""
    matches = _extract_exact_matches(_read_fixture("search_varm.html"), "Varm")

    assert matches == [("VARM", "https://www.eu-startups.com/directory/varm/")]


def test_extract_exact_matches_filters_out_substring_collisions():
    """Real fixture: querying "Minut" returns 9 raw results, only one of
    which ("Minut") case-insensitively equals the query."""
    matches = _extract_exact_matches(_read_fixture("search_minut.html"), "Minut")

    assert matches == [("Minut", "https://www.eu-startups.com/directory/minut/")]


def test_extract_exact_matches_returns_empty_list_for_zero_results():
    matches = _extract_exact_matches(
        _read_fixture("search_zero_results.html"), "Nonexistent Co"
    )

    assert matches == []


def test_extract_exact_matches_returns_every_exact_match_in_document_order():
    matches = _extract_exact_matches(_TWO_EXACT_MATCHES_HTML, "DupeCo")

    assert matches == [
        ("DupeCo", "https://www.eu-startups.com/directory/dupeco/"),
        ("DupeCo", "https://www.eu-startups.com/directory/dupeco-2/"),
    ]


def test_parsed_result_count_reads_the_header_on_every_real_fixture():
    """Confirms the positive (non-truncated) case for all 4 real fixtures:
    each page's own "Search Results (N)" header matches its raw anchor
    count exactly, none of these real captures happen to be truncated."""
    for fixture, expected_count in (
        ("search_brightroom.html", 1),
        ("search_varm.html", 1),
        ("search_minut.html", 9),
        ("search_zero_results.html", 0),
    ):
        html = _read_fixture(fixture)
        assert _parsed_result_count(html) == expected_count
        assert len(_extract_raw_matches(html)) == expected_count


def test_parsed_result_count_returns_none_when_header_is_missing():
    assert _parsed_result_count("<html><body>no header here</body></html>") is None


def test_is_result_set_truncated_true_when_counts_mismatch():
    assert _is_result_set_truncated(raw_match_count=2, parsed_count=5) is True


def test_is_result_set_truncated_true_when_header_not_found():
    assert _is_result_set_truncated(raw_match_count=2, parsed_count=None) is True


def test_is_result_set_truncated_false_when_counts_match():
    assert _is_result_set_truncated(raw_match_count=2, parsed_count=2) is False


def test_eu_startups_enrichment_adapter_explicitly_implements_web_scrape_source_port():
    assert WebScrapeSourcePort in EuStartupsEnrichmentAdapter.__mro__


def test_eu_startups_enrichment_adapter_source_and_mechanism():
    adapter = EuStartupsEnrichmentAdapter(company_loader=lambda: [], max_calls=1)

    assert adapter.source == "eu_startups"
    assert adapter.mechanism == "web_scrape"


def test_fetch_page_raises_sanitized_error_on_request_failure(monkeypatch):
    def fake_get(url, headers, timeout):
        raise requests.ConnectionError("boom")

    monkeypatch.setattr(eu_startups_enrichment.requests, "get", fake_get)
    adapter = EuStartupsEnrichmentAdapter(company_loader=lambda: [], max_calls=1)

    try:
        adapter.fetch_page("https://www.eu-startups.com/directory/brightroom/")
        raise AssertionError("expected EuStartupsEnrichmentFetchError")
    except EuStartupsEnrichmentFetchError as exc:
        assert "ConnectionError" in str(exc)


def test_fetch_enriches_the_single_exact_match(monkeypatch):
    search_html = _read_fixture("search_brightroom.html")
    detail_html = _read_fixture("listing_brightroom.html")
    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: ["Brightroom"], max_calls=5
    )
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _fake_fetch_page(url, search_html, detail_html),
    )

    records = adapter.fetch()

    assert len(records) == 1
    record = records[0]
    assert record.stable_id == "brightroom"
    assert record.payload["html"] == detail_html
    # A valid ISO timestamp parses without raising.
    datetime.fromisoformat(record.payload["lastmod"])


def test_fetch_enriches_a_case_differing_exact_match(monkeypatch):
    """Real fixture: "Varm" query, "VARM" result (proves Constraint 8)."""
    search_html = _read_fixture("search_varm.html")
    detail_html = _read_fixture("listing_varm.html")
    adapter = EuStartupsEnrichmentAdapter(company_loader=lambda: ["Varm"], max_calls=5)
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _fake_fetch_page(url, search_html, detail_html),
    )

    records = adapter.fetch()

    assert len(records) == 1
    assert records[0].stable_id == "varm"


def test_fetch_resolves_a_substring_collision_to_the_one_exact_match(monkeypatch):
    """Real fixture: "Minut" query, 9 raw results, one exact match. Proves
    the exact-match filter runs before the skip rule, not after."""
    search_html = _read_fixture("search_minut.html")
    detail_html = _read_fixture("listing_minut.html")
    adapter = EuStartupsEnrichmentAdapter(company_loader=lambda: ["Minut"], max_calls=5)
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _fake_fetch_page(url, search_html, detail_html),
    )

    records = adapter.fetch()

    assert len(records) == 1
    assert records[0].stable_id == "minut"


def test_fetch_skips_a_company_with_zero_search_results(caplog, monkeypatch):
    search_html = _read_fixture("search_zero_results.html")
    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: ["Nonexistent Co"], max_calls=5
    )
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _fake_fetch_page(url, search_html, "<html></html>"),
    )

    with caplog.at_level(
        logging.INFO, logger="huginn.elt.ingestion.adapters.eu_startups_enrichment"
    ):
        records = adapter.fetch()

    assert records == []
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any("Nonexistent Co" in r.getMessage() for r in infos)


def test_fetch_skips_a_company_with_more_than_one_exact_match(caplog, monkeypatch):
    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: ["DupeCo"], max_calls=5
    )
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _fake_fetch_page(url, _TWO_EXACT_MATCHES_HTML, "<html></html>"),
    )

    with caplog.at_level(
        logging.INFO, logger="huginn.elt.ingestion.adapters.eu_startups_enrichment"
    ):
        records = adapter.fetch()

    assert records == []
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any("DupeCo" in r.getMessage() for r in infos)


def test_fetch_skips_a_company_when_search_results_page_may_be_truncated(
    caplog, monkeypatch
):
    """Header says 5, only 2 raw anchors are present: the truncation guard
    must skip before the exact-match filter ever runs, not fold silently
    into a "0 or many exact matches" INFO skip."""
    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: ["TruncateCo"], max_calls=5
    )
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _fake_fetch_page(
            url, _TRUNCATED_SEARCH_RESULTS_HTML, "<html></html>"
        ),
    )

    with caplog.at_level(
        logging.WARNING, logger="huginn.elt.ingestion.adapters.eu_startups_enrichment"
    ):
        records = adapter.fetch()

    assert records == []
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("TruncateCo" in r.getMessage() for r in warnings)


def test_fetch_skips_a_failed_search_and_continues_with_other_names(
    caplog, monkeypatch
):
    search_html = _read_fixture("search_brightroom.html")
    detail_html = _read_fixture("listing_brightroom.html")
    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: ["Broken Co", "Brightroom"], max_calls=5
    )

    def fake_fetch_page(url: str) -> str:
        if "dosrch=1" in url and "Broken" in url:
            raise eu_startups_enrichment.EuStartupsEnrichmentFetchError("boom")
        return _fake_fetch_page(url, search_html, detail_html)

    monkeypatch.setattr(adapter, "fetch_page", fake_fetch_page)

    with caplog.at_level(
        logging.WARNING, logger="huginn.elt.ingestion.adapters.eu_startups_enrichment"
    ):
        records = adapter.fetch()

    assert len(records) == 1
    assert records[0].stable_id == "brightroom"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Broken Co" in r.getMessage() for r in warnings)


def test_fetch_deduplicates_matching_stable_ids_across_company_names(
    caplog, monkeypatch
):
    """Two different query names, each resolving to exactly one exact
    match, whose detail URLs happen to be the same listing (a plausible
    near-duplicate Gold name for one real company, plan Global
    Constraint 9). The real fixtures have no such pair, so the second
    query's search-results page is a small synthetic snippet (same
    pattern as `_TWO_EXACT_MATCHES_HTML`) whose one exact match points at
    Brightroom's own detail URL.
    """
    brightroom_search_html = _read_fixture("search_brightroom.html")
    brightroom_inc_search_html = """
<h3>Search Results (1)</h3>
<div class="search-results">
  <div class="listing-title"><a href="https://www.eu-startups.com/directory/brightroom/">Brightroom Inc</a></div>
</div>
"""
    detail_html = _read_fixture("listing_brightroom.html")
    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: ["Brightroom", "Brightroom Inc"], max_calls=5
    )

    def fake_fetch_page(url: str) -> str:
        if "dosrch=1" in url:
            return (
                brightroom_inc_search_html if "Inc" in url else brightroom_search_html
            )
        return detail_html

    monkeypatch.setattr(adapter, "fetch_page", fake_fetch_page)

    with caplog.at_level(
        logging.INFO, logger="huginn.elt.ingestion.adapters.eu_startups_enrichment"
    ):
        records = adapter.fetch()

    assert len(records) == 1
    assert records[0].stable_id == "brightroom"
    infos = [r for r in caplog.records if r.levelno == logging.INFO]
    assert any("Brightroom Inc" in r.getMessage() for r in infos)


def test_build_search_url_sends_the_documented_query_params():
    """`_build_search_url` is pure and separate from the actual
    `requests.get` call, so its exact query string is asserted directly
    here rather than by monkeypatching `requests.get` (this codebase's
    `opencorporates.py`/`test_opencorporates.py` pair, by contrast,
    monkeypatches `requests.get` because its URL-building and request-
    sending live in the same function). Mirrors
    `test_opencorporates.py`'s `test_search_companies_requests_expected_url_params_and_timeout`:
    a typo in a field ID here would previously break every real search
    forever while every substring-routed test (`"dosrch=1" in url`) kept
    passing."""
    url = _build_search_url("Acme Robotics")
    parsed = urlparse(url)

    assert f"{parsed.scheme}://{parsed.netloc}{parsed.path}" == (
        eu_startups_enrichment._SEARCH_URL
    )
    assert parse_qs(parsed.query, keep_blank_values=True) == {
        "dosrch": ["1"],
        "q": [""],
        "wpbdp_view": ["search"],
        "listingfields[1]": ["Acme Robotics"],
        "listingfields[2]": ["-1"],
        "listingfields[7]": [""],
        "listingfields[6]": [""],
        "listingfields[4]": ["-1"],
    }


def test_fetch_page_requests_expected_user_agent_and_timeout(monkeypatch):
    """The other half of the live request contract: the confirmed browser
    User-Agent and the configured timeout, on the actual `requests.get`
    call `fetch_page` makes (for both the search request and the detail-
    page fetch, since both route through this one method)."""
    captured = {}

    class FakeResponse:
        text = "<html>ok</html>"

        def raise_for_status(self):
            return None

    def fake_get(url, headers, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr(eu_startups_enrichment.requests, "get", fake_get)
    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: [], max_calls=1, timeout=7.5
    )

    result = adapter.fetch_page("https://www.eu-startups.com/directory/brightroom/")

    assert captured["url"] == "https://www.eu-startups.com/directory/brightroom/"
    assert captured["headers"] == {"User-Agent": eu_startups_enrichment._USER_AGENT}
    assert captured["timeout"] == 7.5
    assert result == "<html>ok</html>"


def test_fetch_stops_after_max_calls(monkeypatch):
    """Mirrors `test_opencorporates.py`'s `test_fetch_stops_after_max_calls`:
    `fetch()` only searches up to `max_calls` names even when given more
    candidates."""
    call_count = {"n": 0}
    zero_results_html = _read_fixture("search_zero_results.html")

    def fake_fetch_page(url: str) -> str:
        call_count["n"] += 1
        return zero_results_html

    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: ["A", "B", "C", "D"], max_calls=2
    )
    monkeypatch.setattr(adapter, "fetch_page", fake_fetch_page)

    adapter.fetch()

    assert call_count["n"] == 2


def test_fetch_skips_when_detail_page_fetch_fails_and_continues_with_other_names(
    caplog, monkeypatch
):
    """The search succeeds with exactly one exact match, but the
    subsequent detail-page `fetch_page` call raises: that name is
    skipped, a WARNING is logged, and it doesn't abort other pending
    names in the same run. Mirrors
    `test_fetch_skips_a_failed_search_and_continues_with_other_names`'s
    structure, moving the injected failure to the detail fetch instead of
    the search request."""
    brightroom_search_html = _read_fixture("search_brightroom.html")
    varm_search_html = _read_fixture("search_varm.html")
    varm_detail_html = _read_fixture("listing_varm.html")
    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: ["Brightroom", "Varm"], max_calls=5
    )

    def fake_fetch_page(url: str) -> str:
        if "dosrch=1" in url:
            return varm_search_html if "Varm" in url else brightroom_search_html
        if "brightroom" in url:
            raise eu_startups_enrichment.EuStartupsEnrichmentFetchError("boom")
        return varm_detail_html

    monkeypatch.setattr(adapter, "fetch_page", fake_fetch_page)

    with caplog.at_level(
        logging.WARNING, logger="huginn.elt.ingestion.adapters.eu_startups_enrichment"
    ):
        records = adapter.fetch()

    assert len(records) == 1
    assert records[0].stable_id == "varm"
    warnings = [r for r in caplog.records if r.levelno == logging.WARNING]
    assert any("Brightroom" in r.getMessage() for r in warnings)
