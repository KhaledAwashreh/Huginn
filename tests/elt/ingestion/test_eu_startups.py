from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from huginn.elt.ingestion.adapters.eu_startups import (
    _parse_listing_sitemap,
    _parse_sitemap_index,
    extract_listing_fields,
)

_FIXTURES = Path(__file__).parent.parent.parent / "fixtures" / "eu_startups"


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


def test_parse_listing_sitemap_returns_loc_and_lastmod_pairs():
    entries = _parse_listing_sitemap(_read_fixture("wpbdp_listing-sitemap165.xml"))

    assert len(entries) > 0
    first_url, first_lastmod = entries[0]
    assert first_url == "https://www.eu-startups.com/directory/brightroom/"
    assert first_lastmod == datetime(2026, 9, 1, 7, 37, 16, tzinfo=UTC)


def test_parse_listing_sitemap_every_entry_has_a_timezone_aware_lastmod():
    entries = _parse_listing_sitemap(_read_fixture("wpbdp_listing-sitemap165.xml"))

    assert all(lastmod.tzinfo is not None for _, lastmod in entries)


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
