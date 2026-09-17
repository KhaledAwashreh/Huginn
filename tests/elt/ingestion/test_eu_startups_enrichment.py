from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import requests

from huginn.elt.ingestion.adapters import eu_startups_enrichment
from huginn.elt.ingestion.adapters.eu_startups_enrichment import (
    EuStartupsEnrichmentAdapter,
    EuStartupsEnrichmentFetchError,
    _extract_exact_matches,
)
from huginn.elt.ingestion.ports import WebScrapeSourcePort

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "eu_startups"

# No live query produced a ">1 exact match" page; a small, hand-written
# fragment reusing the real `.search-results .listing-title a` structure
# (plan Global Constraint 11, same pattern as
# `test_eu_startups_staging.py`'s field-free fragment).
_TWO_EXACT_MATCHES_HTML = """
<div class="search-results">
  <div class="listing-title"><a href="https://www.eu-startups.com/directory/dupeco/">DupeCo</a></div>
  <div class="listing-title"><a href="https://www.eu-startups.com/directory/dupeco-2/">DupeCo</a></div>
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


def test_fetch_deduplicates_matching_stable_ids_across_company_names(monkeypatch):
    search_html = _read_fixture("search_brightroom.html")
    detail_html = _read_fixture("listing_brightroom.html")
    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: ["Brightroom", "Brightroom Inc"], max_calls=5
    )
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _fake_fetch_page(url, search_html, detail_html),
    )

    records = adapter.fetch()

    assert len(records) == 1
    assert records[0].stable_id == "brightroom"
