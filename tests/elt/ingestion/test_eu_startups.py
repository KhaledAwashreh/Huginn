from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from huginn.elt.ingestion.adapters.eu_startups import (
    _parse_listing_sitemap,
    _parse_sitemap_index,
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
