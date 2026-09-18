from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from huginn.elt.silver.eu_startups_staging import (
    EuStartupsStagingLoader,
    parse_eu_startups_listing,
)

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "eu_startups"

# Real lastmod for brightroom's entry in wpbdp_listing-sitemap165.xml
# (confirmed by inspecting the fixture directly), used so occurred_on can
# be tested against a real value rather than a guess.
_BRIGHTROOM_LASTMOD = "2026-09-01T07:37:16+00:00"


def _payload(html_name: str, url: str, lastmod: str = _BRIGHTROOM_LASTMOD) -> dict:
    """Bronze payload shape, per Global Constraint 4 of the KAN-64 plan:
    `{"url", "html", "lastmod"}`, `lastmod` an ISO 8601 string (the
    ingestion adapter's `RawRecord.payload` now carries all three, see
    huginn.elt.ingestion.adapters.eu_startups.EuStartupsDiscoveryAdapter.fetch)."""
    return {
        "url": url,
        "html": (_FIXTURES / html_name).read_text(),
        "lastmod": lastmod,
    }


def test_parse_eu_startups_listing_maps_every_confirmed_field():
    row = parse_eu_startups_listing(
        _payload(
            "listing_brightroom.html",
            "https://www.eu-startups.com/directory/brightroom/",
        )
    )

    assert row is not None
    assert row.company_name_raw == "Brightroom"
    assert row.website == "https://thebrightroom.de"
    assert row.url == "https://www.eu-startups.com/directory/brightroom/"
    assert row.occurred_on == datetime(2026, 9, 1, 7, 37, 16, tzinfo=UTC)


def test_parse_eu_startups_listing_handles_missing_optional_fields():
    row = parse_eu_startups_listing(
        _payload("listing_minut.html", "https://www.eu-startups.com/directory/minut/")
    )

    assert row is not None
    assert row.website == "https://minut.com/"
    assert row.company_name_raw == "Minut"


def test_parse_eu_startups_listing_returns_none_when_no_website_field_at_all():
    """A payload whose HTML has no wpbdp fields at all (a malformed or
    unexpected fetch) yields no staging row rather than a row full of
    None/empty values that would fail resolve_signal's own handling
    downstream."""
    row = parse_eu_startups_listing(
        {
            "url": "https://www.eu-startups.com/directory/broken/",
            "html": "<html></html>",
        }
    )

    assert row is None


def test_parse_eu_startups_listing_returns_none_for_interstitial_page_with_title():
    """A Cloudflare interstitial or soft-404 page has a `<title>` tag but
    no wpbdp field markup at all (no Website, which is confirmed always
    present on a genuine listing). It must not pass through as a
    fabricated company with website=None just because a title was found."""
    row = parse_eu_startups_listing(
        {
            "url": "https://www.eu-startups.com/directory/broken/",
            "html": "<html><head><title>Just a moment...</title></head><body></body></html>",
            "lastmod": _BRIGHTROOM_LASTMOD,
        }
    )

    assert row is None


def test_parse_eu_startups_listing_returns_none_when_lastmod_key_missing():
    """A payload missing the `lastmod` key entirely (not just a `None`
    value), same bug class as KAN-50: must not raise a `KeyError` that
    would abort every already-upserted row in the batch. A listing with no
    recorded lastmod is not safely parseable into `occurred_on`, which is
    NOT NULL downstream in Gold, so it is skipped rather than crashing."""
    payload = _payload(
        "listing_brightroom.html",
        "https://www.eu-startups.com/directory/brightroom/",
    )
    del payload["lastmod"]

    row = parse_eu_startups_listing(payload)

    assert row is None


def test_parse_eu_startups_listing_returns_none_when_lastmod_is_unparseable():
    """A payload whose `lastmod` key is present but not a valid ISO 8601
    string (e.g. an empty string from a malformed sitemap entry) must be
    skipped like a missing `lastmod`, not raise an uncaught `ValueError`
    from `datetime.fromisoformat` that would abort the whole batch (same
    KAN-50 bug class as the missing-key case above, triggered by a
    malformed value instead of a missing one; CodeRabbit finding, KAN-64)."""
    payload = _payload(
        "listing_brightroom.html",
        "https://www.eu-startups.com/directory/brightroom/",
        lastmod="",
    )

    row = parse_eu_startups_listing(payload)

    assert row is None


class FakeEuStartupsStagingRepository:
    def __init__(self, bronze_rows):
        self._bronze_rows = bronze_rows
        self.upserted = []

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_value, traceback):
        return None

    def read(self, source):
        return self._bronze_rows

    def upsert(self, row):
        self.upserted.append(row)


def test_loader_upserts_one_row_per_parseable_bronze_payload():
    repository = FakeEuStartupsStagingRepository(
        bronze_rows=[
            _payload(
                "listing_brightroom.html",
                "https://www.eu-startups.com/directory/brightroom/",
            ),
            _payload(
                "listing_minut.html", "https://www.eu-startups.com/directory/minut/"
            ),
        ]
    )
    loader = EuStartupsStagingLoader(repository)

    written = loader.load()

    assert written == 2
    assert len(repository.upserted) == 2


def test_loader_skips_an_unparseable_bronze_payload_without_upserting_it():
    """A Bronze row `parse_eu_startups_listing` can't parse (an interstitial
    page with no wpbdp fields, same shape the parser-level tests above
    already cover) must be excluded from both the loader's returned count
    and its upsert calls, not just from the parser's own return value."""
    repository = FakeEuStartupsStagingRepository(
        bronze_rows=[
            _payload(
                "listing_brightroom.html",
                "https://www.eu-startups.com/directory/brightroom/",
            ),
            {
                "url": "https://www.eu-startups.com/directory/broken/",
                "html": "<html><head><title>Just a moment...</title></head></html>",
                "lastmod": _BRIGHTROOM_LASTMOD,
            },
        ]
    )
    loader = EuStartupsStagingLoader(repository)

    written = loader.load()

    assert written == 1
    assert len(repository.upserted) == 1
