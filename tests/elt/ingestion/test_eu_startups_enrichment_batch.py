from pathlib import Path

from huginn.elt.ingestion.adapters.eu_startups_enrichment import (
    EuStartupsEnrichmentAdapter,
    EuStartupsEnrichmentFetchError,
)
from huginn.elt.ingestion.models import EnrichmentOutcomeStatus

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "eu_startups"


def _read_fixture(name: str) -> str:
    return (_FIXTURES / name).read_text(encoding="utf-8")


def test_fetch_batch_marks_only_definitive_outcomes_as_cursor_advancing(monkeypatch):
    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: [
            "Missing Co",
            "Brightroom",
            "Transient Co",
            "Detail Error Co",
        ],
        max_calls=10,
    )

    def fake_fetch_page(url: str) -> str:
        if "dosrch=1" in url:
            if "Transient" in url:
                raise EuStartupsEnrichmentFetchError("temporary search failure")
            if "Detail+Error" in url or "Detail%20Error" in url:
                return """<h3>Search Results (1)</h3><div class="search-results">
                  <div class="listing-title"><a href="https://www.eu-startups.com/directory/detail-error-co/">Detail Error Co</a></div>
                </div>"""
            if "Brightroom" in url:
                return _read_fixture("search_brightroom.html")
            return _read_fixture("search_zero_results.html")
        if "detail-error-co" in url:
            raise EuStartupsEnrichmentFetchError("temporary detail failure")
        return _read_fixture("listing_brightroom.html")

    monkeypatch.setattr(adapter, "fetch_page", fake_fetch_page)

    batch = adapter.fetch_batch()

    assert [outcome.name for outcome in batch.outcomes] == [
        "Missing Co",
        "Brightroom",
        "Transient Co",
        "Detail Error Co",
    ]
    assert [outcome.status for outcome in batch.outcomes] == [
        EnrichmentOutcomeStatus.NO_EXACT_MATCH,
        EnrichmentOutcomeStatus.ENRICHED,
        EnrichmentOutcomeStatus.SEARCH_FAILED,
        EnrichmentOutcomeStatus.DETAIL_FETCH_FAILED,
    ]
    assert batch.definitive_names == ("Missing Co", "Brightroom")
    assert len(batch.records) == 1


def test_http_success_challenge_detail_is_retryable_and_not_persisted(monkeypatch):
    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: ["Brightroom"], max_calls=1
    )
    challenge_html = """<!doctype html>
    <html><head><title>Just a moment...</title></head>
    <body><div id="challenge-form">Checking your browser</div></body></html>"""

    def fake_fetch_page(url: str) -> str:
        if "dosrch=1" in url:
            return _read_fixture("search_brightroom.html")
        return challenge_html

    monkeypatch.setattr(adapter, "fetch_page", fake_fetch_page)

    batch = adapter.fetch_batch()

    assert batch.records == ()
    assert [outcome.status for outcome in batch.outcomes] == [
        EnrichmentOutcomeStatus.DETAIL_INVALID
    ]
    assert batch.definitive_names == ()


def test_duplicate_stable_id_is_definitive_for_both_candidate_names(monkeypatch):
    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: ["Brightroom", "Brightroom Inc"], max_calls=5
    )
    second_search = """
    <h3>Search Results (1)</h3><div class="search-results">
      <div class="listing-title"><a href="https://www.eu-startups.com/directory/brightroom/">Brightroom Inc</a></div>
    </div>
    """

    def fake_fetch_page(url: str) -> str:
        if "dosrch=1" in url:
            return (
                second_search
                if "Brightroom+Inc" in url
                else _read_fixture("search_brightroom.html")
            )
        return _read_fixture("listing_brightroom.html")

    monkeypatch.setattr(adapter, "fetch_page", fake_fetch_page)

    batch = adapter.fetch_batch()

    assert [outcome.status for outcome in batch.outcomes] == [
        EnrichmentOutcomeStatus.ENRICHED,
        EnrichmentOutcomeStatus.DUPLICATE_STABLE_ID,
    ]
    assert batch.definitive_names == ("Brightroom", "Brightroom Inc")
    assert len(batch.records) == 1


def test_fetch_batch_classifies_multiple_invalid_and_incomplete_results(monkeypatch):
    adapter = EuStartupsEnrichmentAdapter(
        company_loader=lambda: ["DupeCo", "InvalidCo", "TruncateCo"],
        max_calls=5,
    )
    multiple = """<h3>Search Results (2)</h3><div class="search-results">
      <div class="listing-title"><a href="https://www.eu-startups.com/directory/dupe-1/">DupeCo</a></div>
      <div class="listing-title"><a href="https://www.eu-startups.com/directory/dupe-2/">DupeCo</a></div>
    </div>"""
    invalid = """<h3>Search Results (1)</h3><div class="search-results">
      <div class="listing-title"><a href="https://evil.example/directory/invalid/">InvalidCo</a></div>
    </div>"""
    truncated = """<h3>Search Results (3)</h3><div class="search-results">
      <div class="listing-title"><a href="https://www.eu-startups.com/directory/truncated/">TruncateCo</a></div>
    </div>"""

    def fake_fetch_page(url: str) -> str:
        if "DupeCo" in url:
            return multiple
        if "InvalidCo" in url:
            return invalid
        return truncated

    monkeypatch.setattr(adapter, "fetch_page", fake_fetch_page)

    batch = adapter.fetch_batch()

    assert [outcome.status for outcome in batch.outcomes] == [
        EnrichmentOutcomeStatus.MULTIPLE_EXACT_MATCHES,
        EnrichmentOutcomeStatus.INVALID_DETAIL_URL,
        EnrichmentOutcomeStatus.SEARCH_INCOMPLETE,
    ]
    assert batch.definitive_names == ("DupeCo", "InvalidCo")
