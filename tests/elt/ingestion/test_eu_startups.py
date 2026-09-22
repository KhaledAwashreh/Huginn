from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

import pytest

from huginn.elt.ingestion.adapters import eu_startups
from huginn.elt.ingestion.adapters.eu_startups import (
    EuStartupsDiscoveryAdapter,
    EuStartupsFetchError,
    _listing_slug,
    _parse_listing_sitemap,
    _parse_sitemap_index,
    extract_listing_fields,
)
from huginn.elt.ingestion.models import DiscoveryBatch, FailedListingOutcome, RawRecord

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "eu_startups"

# The real sitemap_index.xml fixture lists 165 wpbdp_listing-sitemap files;
# routing every one of them to the real wpbdp_listing-sitemap165.xml fixture
# (87 entries) would mean fetch() processes 165 * 87 detail pages per test.
# The plan (Task 3, Step 1 note) explicitly allows trimming the index to a
# small hand-written fixture instead, to keep these tests fast without
# losing what they prove (watermark filtering, stable_id shape, save-once
# behavior). Two entries, both routed to the same real per-sitemap fixture,
# still exercises "walk every listing sitemap the index lists".
_SMALL_SITEMAP_INDEX_XML = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://www.eu-startups.com/wpbdp_listing-sitemap164.xml</loc></sitemap>
<sitemap><loc>https://www.eu-startups.com/wpbdp_listing-sitemap165.xml</loc></sitemap>
</sitemapindex>"""

# The true maximum `lastmod` across every entry in wpbdp_listing-sitemap165.xml
# (confirmed by inspecting the fixture directly), used to test "nothing newer
# than the watermark" without guessing at a value.
_MAX_FIXTURE_LASTMOD = "2026-09-09T15:04:35+00:00"


def _fake_fetch_page(url: str, listing_sitemap_xml: str, detail_html: str) -> str:
    """Route a monkeypatched `fetch_page` call by URL shape: the sitemap
    index URL gets the small hand-written index above, any
    `wpbdp_listing-sitemap*.xml` URL gets the preloaded real per-sitemap
    fixture, everything else (a listing detail page) gets the preloaded
    detail-page fixture. Fixtures are read once by the caller and passed
    in, not re-read per call, so repeated routing stays cheap.
    """
    if "sitemap_index" in url:
        return _SMALL_SITEMAP_INDEX_XML
    if "wpbdp_listing-sitemap" in url:
        return listing_sitemap_xml
    return detail_html


def _read_fixture(name: str) -> str:
    return (_FIXTURES / name).read_text()


def test_parse_sitemap_index_returns_only_wpbdp_listing_sitemaps():
    urls = _parse_sitemap_index(_read_fixture("sitemap_index.xml"))

    assert len(urls) == 165
    assert all("wpbdp_listing-sitemap" in url for url in urls)
    assert "https://www.eu-startups.com/wpbdp_listing-sitemap165.xml" in urls


def test_parse_sitemap_index_does_not_include_post_or_job_sitemaps():
    urls = _parse_sitemap_index(_read_fixture("sitemap_index.xml"))

    assert not any("post-sitemap" in url for url in urls)
    assert not any("job-sitemap" in url for url in urls)


def test_parse_sitemap_index_rejects_untrusted_listing_sitemap_urls():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>http://169.254.169.254/wpbdp_listing-sitemap.xml</loc></sitemap>
<sitemap><loc>https://www.eu-startups.com.evil.example/wpbdp_listing-sitemap.xml</loc></sitemap>
<sitemap><loc>https://www.eu-startups.com/wpbdp_listing-sitemap165.xml</loc></sitemap>
</sitemapindex>"""

    assert _parse_sitemap_index(xml) == [
        "https://www.eu-startups.com/wpbdp_listing-sitemap165.xml"
    ]


def test_parse_listing_sitemap_returns_loc_and_lastmod_pairs():
    entries = _parse_listing_sitemap(_read_fixture("wpbdp_listing-sitemap165.xml"))

    assert len(entries) > 0
    first_url, first_lastmod = entries[0]
    assert first_url == "https://www.eu-startups.com/directory/brightroom/"
    assert first_lastmod == datetime(2026, 9, 1, 7, 37, 16, tzinfo=UTC)


def test_parse_listing_sitemap_rejects_untrusted_detail_urls():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>http://127.0.0.1/admin</loc><lastmod>2026-09-01T00:00:00+00:00</lastmod></url>
<url><loc>https://www.eu-startups.com/about/</loc><lastmod>2026-09-01T00:00:00+00:00</lastmod></url>
<url><loc>https://www.eu-startups.com/directory/../</loc><lastmod>2026-09-01T00:00:00+00:00</lastmod></url>
<url><loc>https://www.eu-startups.com/directory/%2E%2E/</loc><lastmod>2026-09-01T00:00:00+00:00</lastmod></url>
<url><loc>https://www.eu-startups.com/directory/%2Fadmin/</loc><lastmod>2026-09-01T00:00:00+00:00</lastmod></url>
<url><loc>https://www.eu-startups.com/directory/%FF/</loc><lastmod>2026-09-01T00:00:00+00:00</lastmod></url>
<url><loc>https://www.eu-startups.com/directory/%/</loc><lastmod>2026-09-01T00:00:00+00:00</lastmod></url>
<url><loc>https://www.eu-startups.com/directory/%G0/</loc><lastmod>2026-09-01T00:00:00+00:00</lastmod></url>
<url><loc>https://www.eu-startups.com/directory/%0/</loc><lastmod>2026-09-01T00:00:00+00:00</lastmod></url>
<url><loc>https://www.eu-startups.com/directory/brightroom/</loc><lastmod>2026-09-01T00:00:00+00:00</lastmod></url>
</urlset>"""

    entries = _parse_listing_sitemap(xml)

    assert entries == [
        (
            "https://www.eu-startups.com/directory/brightroom/",
            datetime(2026, 9, 1, tzinfo=UTC),
        )
    ]


def test_listing_slug_decodes_a_valid_percent_escape():
    assert (
        _listing_slug("https://www.eu-startups.com/directory/brightroom%2Dlabs/")
        == "brightroom-labs"
    )


def test_parse_listing_sitemap_every_entry_has_a_timezone_aware_lastmod():
    entries = _parse_listing_sitemap(_read_fixture("wpbdp_listing-sitemap165.xml"))

    assert all(lastmod.tzinfo is not None for _, lastmod in entries)


def test_parse_listing_sitemap_skips_invalid_or_timezone_naive_lastmod():
    xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.eu-startups.com/directory/malformed/</loc><lastmod>not-a-date</lastmod></url>
<url><loc>https://www.eu-startups.com/directory/naive/</loc><lastmod>2026-09-01T00:00:00</lastmod></url>
<url><loc>https://www.eu-startups.com/directory/valid/</loc><lastmod>2026-09-01T00:00:00+00:00</lastmod></url>
</urlset>"""

    assert _parse_listing_sitemap(xml) == [
        (
            "https://www.eu-startups.com/directory/valid/",
            datetime(2026, 9, 1, tzinfo=UTC),
        )
    ]


def test_extract_listing_fields_gets_every_field_when_all_present():
    fields = extract_listing_fields(_read_fixture("listing_brightroom.html"))

    assert fields["category"] == "Germany"
    assert "invite-only coaching marketplace" in fields["business_description"]
    assert fields["long_business_description"] is not None
    assert (
        "curated, invite-only coaching marketplace"
        in fields["long_business_description"]
    )
    assert fields["based_in"] == "Berlin"
    assert (
        fields["tags"]
        == "coaching, marketplace, career development, professional development, invite-only"
    )
    assert fields["total_funding"] == "No funding announced yet"
    assert fields["founded"] == "2024"
    assert fields["website"] == "https://thebrightroom.de"
    assert fields["company_status"] == "Active"


def test_extract_listing_fields_leaves_optional_fields_none_when_absent():
    fields = extract_listing_fields(_read_fixture("listing_minut.html"))

    assert fields["category"] == "Sweden"
    assert fields["based_in"] == "Malmo"
    assert fields["founded"] == "2014"
    assert fields["website"] == "https://minut.com/"
    assert fields["tags"] is None
    assert fields["total_funding"] is None
    assert fields["company_status"] is None
    assert fields["long_business_description"] is None


def test_extract_listing_fields_never_raises_on_a_field_free_fragment():
    """An empty or unrelated HTML document has no wpbdp-field elements at
    all; every key must still be present, all values None, no exception."""
    fields = extract_listing_fields("<html><body>not a listing</body></html>")

    assert fields["category"] is None
    assert fields["website"] is None
    assert set(fields.keys()) == {
        "category",
        "business_description",
        "long_business_description",
        "based_in",
        "tags",
        "total_funding",
        "founded",
        "website",
        "company_status",
    }


def test_fetch_page_rejects_redirects(monkeypatch):
    captured = {}

    class FakeRedirectResponse:
        status_code = 304

        def raise_for_status(self):
            return None

    def fake_get(url, headers, timeout, allow_redirects):
        captured["allow_redirects"] = allow_redirects
        return FakeRedirectResponse()

    monkeypatch.setattr(eu_startups.requests, "get", fake_get)
    adapter = EuStartupsDiscoveryAdapter()

    with pytest.raises(EuStartupsFetchError, match="redirect"):
        adapter.fetch_page("https://www.eu-startups.com/directory/brightroom/")

    assert captured["allow_redirects"] is False


def test_fetch_page_preserves_confirmed_http_status_for_retry_policy(monkeypatch):
    class FakeNotFoundResponse:
        status_code = 404

        def __bool__(self):
            return False

        def raise_for_status(self):
            raise eu_startups.requests.HTTPError(response=self)

    monkeypatch.setattr(
        eu_startups.requests,
        "get",
        lambda _url, **_kwargs: FakeNotFoundResponse(),
    )
    adapter = EuStartupsDiscoveryAdapter()

    with pytest.raises(EuStartupsFetchError) as exc_info:
        adapter.fetch_page("https://www.eu-startups.com/directory/missing/")

    assert exc_info.value.status_code == 404


def test_fetch_processes_every_listing_when_no_watermark_yet(monkeypatch):
    listing_sitemap_xml = _read_fixture("wpbdp_listing-sitemap165.xml")
    detail_html = _read_fixture("listing_brightroom.html")
    adapter = EuStartupsDiscoveryAdapter()
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _fake_fetch_page(url, listing_sitemap_xml, detail_html),
    )

    batch = adapter.fetch(watermark=None)

    assert len(batch.records) > 0
    assert all(record.stable_id for record in batch.records)
    assert batch.proposed_watermark == _MAX_FIXTURE_LASTMOD
    assert batch.failed_listings == ()


def test_fetch_skips_listings_at_or_before_the_watermark(monkeypatch):
    """A watermark at or after the maximum lastmod in the fixture means
    nothing new to process (comparison is `lastmod > watermark`, so a
    watermark equal to the maximum still excludes it)."""
    listing_sitemap_xml = _read_fixture("wpbdp_listing-sitemap165.xml")
    detail_html = _read_fixture("listing_brightroom.html")
    adapter = EuStartupsDiscoveryAdapter()
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _fake_fetch_page(url, listing_sitemap_xml, detail_html),
    )

    batch = adapter.fetch(watermark=_MAX_FIXTURE_LASTMOD)

    assert batch == DiscoveryBatch((), None, ())


def test_discovery_batch_models_are_immutable():
    record = RawRecord(stable_id="brightroom", payload={"html": "<html>"})
    failure = FailedListingOutcome(
        url="https://www.eu-startups.com/directory/broken-listing/",
        lastmod="2026-09-05T00:00:00+00:00",
        status_code=404,
    )
    batch = DiscoveryBatch((record,), "2026-09-05T00:00:00+00:00", (failure,))

    with pytest.raises(AttributeError):
        batch.proposed_watermark = None

    with pytest.raises(AttributeError):
        failure.status_code = None

    assert batch.records == (record,)
    assert batch.failed_listings == (failure,)


def test_fetch_proposes_the_new_watermark_without_persisting_it(monkeypatch):
    listing_sitemap_xml = _read_fixture("wpbdp_listing-sitemap165.xml")
    detail_html = _read_fixture("listing_brightroom.html")
    adapter = EuStartupsDiscoveryAdapter()
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _fake_fetch_page(url, listing_sitemap_xml, detail_html),
    )

    batch = adapter.fetch(watermark=None)

    assert batch.proposed_watermark == _MAX_FIXTURE_LASTMOD


def test_fetch_skips_a_listing_whose_detail_page_fetch_fails(monkeypatch):
    """One permanently-broken listing (404/410) must not abort the whole
    run: the other, successfully-fetched listing's record is still
    returned. The failed listing's lastmod is chronologically later than
    the successful one's here, so the saved watermark must be pinned to
    just before the failure (not the successful listing's own, earlier
    lastmod, and not the failed listing's lastmod itself), so the failed
    listing remains eligible for retry next run rather than being
    coincidentally skipped."""
    sitemap_index_xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://www.eu-startups.com/wpbdp_listing-sitemap-test.xml</loc></sitemap>
</sitemapindex>"""
    listing_sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.eu-startups.com/directory/good-listing/</loc><lastmod>2026-09-01T00:00:00+00:00</lastmod></url>
<url><loc>https://www.eu-startups.com/directory/broken-listing/</loc><lastmod>2026-09-05T00:00:00+00:00</lastmod></url>
</urlset>"""
    detail_html = _read_fixture("listing_brightroom.html")

    def fake_fetch_page(url: str) -> str:
        if "sitemap_index" in url:
            return sitemap_index_xml
        if "wpbdp_listing-sitemap" in url:
            return listing_sitemap_xml
        if "broken-listing" in url:
            raise EuStartupsFetchError("simulated 404", status_code=404)
        return detail_html

    adapter = EuStartupsDiscoveryAdapter()
    monkeypatch.setattr(adapter, "fetch_page", fake_fetch_page)

    batch = adapter.fetch(watermark=None)

    assert len(batch.records) == 1
    assert batch.records[0].stable_id == "good-listing"
    assert batch.proposed_watermark == "2026-09-04T23:59:59+00:00"
    assert batch.failed_listings == (
        FailedListingOutcome(
            url="https://www.eu-startups.com/directory/broken-listing/",
            lastmod="2026-09-05T00:00:00+00:00",
            status_code=404,
        ),
    )


def test_fetch_keeps_an_earlier_failure_eligible_for_retry_past_a_later_success(
    monkeypatch,
):
    """CodeRabbit finding (KAN-64): three pending listings, lastmods in
    order A < B < C. B fails, A and C succeed. The naive fix (max lastmod
    across successes only) would save C's lastmod as the new watermark,
    which is already past B's lastmod, permanently excluding B from the
    `lastmod > watermark` filter on every future run even though it was
    never actually fetched. The saved watermark must instead be strictly
    less than B's lastmod, so B remains eligible for retry next run."""
    sitemap_index_xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://www.eu-startups.com/wpbdp_listing-sitemap-test.xml</loc></sitemap>
</sitemapindex>"""
    listing_sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.eu-startups.com/directory/listing-a/</loc><lastmod>2026-09-01T00:00:00+00:00</lastmod></url>
<url><loc>https://www.eu-startups.com/directory/listing-b/</loc><lastmod>2026-09-03T00:00:00+00:00</lastmod></url>
<url><loc>https://www.eu-startups.com/directory/listing-c/</loc><lastmod>2026-09-05T00:00:00+00:00</lastmod></url>
</urlset>"""
    detail_html = _read_fixture("listing_brightroom.html")

    def fake_fetch_page(url: str) -> str:
        if "sitemap_index" in url:
            return sitemap_index_xml
        if "wpbdp_listing-sitemap" in url:
            return listing_sitemap_xml
        if "listing-b" in url:
            raise EuStartupsFetchError("simulated 404")
        return detail_html

    adapter = EuStartupsDiscoveryAdapter()
    monkeypatch.setattr(adapter, "fetch_page", fake_fetch_page)

    batch = adapter.fetch(watermark=None)

    assert {record.stable_id for record in batch.records} == {"listing-a", "listing-c"}
    listing_b_lastmod = datetime(2026, 9, 3, 0, 0, 0, tzinfo=UTC)
    assert datetime.fromisoformat(batch.proposed_watermark) < listing_b_lastmod
    assert batch.failed_listings == (
        FailedListingOutcome(
            url="https://www.eu-startups.com/directory/listing-b/",
            lastmod="2026-09-03T00:00:00+00:00",
            status_code=None,
        ),
    )


def test_fetch_does_not_regress_a_fractional_second_watermark_on_failure(
    monkeypatch,
):
    incoming_watermark = "2026-09-03T00:00:00.900000+00:00"
    sitemap_index_xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://www.eu-startups.com/wpbdp_listing-sitemap-test.xml</loc></sitemap>
</sitemapindex>"""
    listing_sitemap_xml = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<url><loc>https://www.eu-startups.com/directory/failed-listing/</loc><lastmod>2026-09-03T00:00:01+00:00</lastmod></url>
</urlset>"""

    def fake_fetch_page(url: str) -> str:
        if "sitemap_index" in url:
            return sitemap_index_xml
        if "wpbdp_listing-sitemap" in url:
            return listing_sitemap_xml
        raise EuStartupsFetchError("simulated network failure")

    adapter = EuStartupsDiscoveryAdapter()
    monkeypatch.setattr(adapter, "fetch_page", fake_fetch_page)

    batch = adapter.fetch(watermark=incoming_watermark)

    assert batch.records == ()
    assert batch.proposed_watermark == incoming_watermark
    assert datetime.fromisoformat(
        batch.failed_listings[0].lastmod
    ) > datetime.fromisoformat(batch.proposed_watermark)


def test_fetch_raises_when_sitemap_index_lists_zero_listing_sitemaps(monkeypatch):
    """An index that parses to zero `wpbdp_listing-sitemap` entries (e.g. a
    namespace variant the hardcoded qualified tags don't match) is a
    genuine discovery failure, not "nothing new since last run", and must
    be loud rather than silently returning []."""
    empty_index_xml = """<?xml version="1.0" encoding="UTF-8"?>
<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
<sitemap><loc>https://www.eu-startups.com/post-sitemap.xml</loc></sitemap>
</sitemapindex>"""
    adapter = EuStartupsDiscoveryAdapter()
    monkeypatch.setattr(adapter, "fetch_page", lambda url: empty_index_xml)

    with pytest.raises(EuStartupsFetchError):
        adapter.fetch(watermark=None)


def test_raw_record_stable_id_is_the_listing_slug_not_the_full_url(monkeypatch):
    listing_sitemap_xml = _read_fixture("wpbdp_listing-sitemap165.xml")
    detail_html = _read_fixture("listing_brightroom.html")
    adapter = EuStartupsDiscoveryAdapter()
    monkeypatch.setattr(
        adapter,
        "fetch_page",
        lambda url: _fake_fetch_page(url, listing_sitemap_xml, detail_html),
    )

    batch = adapter.fetch(watermark=None)

    assert all("/" not in record.stable_id for record in batch.records)
    assert all(not record.stable_id.startswith("http") for record in batch.records)
