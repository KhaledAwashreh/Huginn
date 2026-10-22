from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path

from huginn.elt.silver.context.eu_startups import normalize_eu_startups

_FIXTURE = (
    Path(__file__).parents[3] / "fixtures" / "eu_startups" / "listing_brightroom.html"
)
_URL = "https://www.eu-startups.com/directory/brightroom/"
_LASTMOD = "2026-09-01T07:37:16+00:00"


def _payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "url": _URL,
        "html": _FIXTURE.read_text(encoding="utf-8"),
        "lastmod": _LASTMOD,
    }
    payload.update(overrides)
    return payload


def test_normalizer_preserves_listing_fields_and_distinct_descriptions() -> None:
    result = normalize_eu_startups(_payload())

    assert result.source == "eu_startups"
    assert result.stable_id == "brightroom"
    assert result.status == "captured"
    assert result.source_url == _URL
    assert result.normalized_text
    assert result.source_times == {
        "lastmod": datetime(2026, 9, 1, 7, 37, 16, tzinfo=UTC)
    }
    assert result.source_fields == {
        "short_description": (
            "An invite-only coaching marketplace for individual professionals in "
            "Europe. Coaches are recommended by past clients and personally approved "
            "by the founder to meet qualification and experience criteria. Published, "
            "fixed pricing."
        ),
        "long_description": (
            "Brightroom is a curated, invite-only coaching marketplace for individual "
            "professionals across Europe. Every coach is recommended by a past client, "
            "then personally reviewed and approved by the founder - an ICF accredited "
            "coach with a Master's in Psychology. There is no open sign-up and no way "
            "to pay your way onto the list. Free discovery call with any coach. Prices "
            "are published upfront. One package gives access to all coaches on the "
            "platform."
        ),
        "category": "Germany",
        "place": "Berlin",
        "tags": "coaching, marketplace, career development, professional development, invite-only",
        "website": "https://thebrightroom.de",
        "founded": "2024",
        "funding": "No funding announced yet",
        "status": "Active",
    }
    assert "Brightroom" in result.normalized_text
    assert "Categories" not in result.normalized_text
    assert "Subscribe to our newsletter" not in result.normalized_text


def test_missing_optional_fields_remain_unknown() -> None:
    html = """<html><head><title>Example | EU-Startups</title></head><body>
      <div class="wpbdp-listing-single">
        <div class="wpbdp-field-category"><div class="value">Mobility</div></div>
        <div class="wpbdp-field-website"><div class="value">https://example.test</div></div>
      </div></body></html>"""

    result = normalize_eu_startups(
        {"url": "https://www.eu-startups.com/directory/example/", "html": html}
    )

    assert result.status == "captured"
    assert result.source_fields["category"] == "Mobility"
    assert result.source_fields["short_description"] is None
    assert result.source_fields["long_description"] is None
    assert result.source_fields["place"] is None
    assert "country" not in result.source_fields
    assert result.source_times == {}


def test_repeated_or_reordered_fields_keep_listing_scoped_values() -> None:
    html = """<html><body><nav><div class="wpbdp-field-website"><div class="value">https://wrong.test</div></div></nav>
      <div class="wpbdp-listing-single">
        <div class="wpbdp-field-website"><div class="value"><a href="https://right.test">Visit</a></div></div>
        <div class="wpbdp-field-business_description"><div class="value"><p>First</p><p>second</p></div></div>
        <div class="wpbdp-field-category"><div class="value"><a>Health</a>, Climate</div></div>
      </div></body></html>"""

    result = normalize_eu_startups(
        {"url": "https://www.eu-startups.com/directory/example/", "html": html}
    )

    assert result.status == "captured"
    assert result.source_fields["website"] == "https://right.test"
    assert result.source_fields["website_label"] == "Visit"
    assert result.source_fields["short_description"] == "First second"
    assert result.source_fields["category"] == "Health, Climate"


def test_website_field_does_not_accept_malformed_or_internal_links() -> None:
    for href in (
        "javascript:alert(1)",
        "//outside.example/site",
        "https://user:secret@outside.example/site",
        "https://www.eu-startups.com/directory/other/",
        "https://outside.example:bad-port/site",
    ):
        html = f"""<html><body><div class="wpbdp-listing-single">
          <div class="wpbdp-field-website"><div class="value">
            <a href="{href}">Visit company website</a>
          </div></div>
          <div class="wpbdp-field-category"><div class="value">Health</div></div>
        </div></body></html>"""

        result = normalize_eu_startups({"url": _URL, "html": html})

        assert result.status == "captured"
        assert result.source_fields["website"] is None
        assert result.source_fields["website_label"] == "Visit company website"


def test_off_domain_listing_url_is_rejected() -> None:
    result = normalize_eu_startups(
        {
            "url": "https://evil.example/directory/example/",
            "html": _payload()["html"],
        }
    )

    assert result.status == "failed"
    assert result.stable_id is None


def test_navigation_only_or_unstructured_pages_are_not_evidence() -> None:
    result = normalize_eu_startups(
        {
            "url": _URL,
            "html": "<html><body><nav>Startups Directory Subscribe</nav><footer>Contact</footer></body></html>",
        }
    )

    assert result.status == "failed"
    assert result.stable_id == "brightroom"
    assert result.source_fields == {}
    assert result.normalized_text is None


def test_malformed_payload_is_reported_without_raising() -> None:
    result = normalize_eu_startups({"url": _URL, "html": "<html>", "lastmod": 42})

    assert result.status == "failed"
    assert result.reason
    assert result.normalized_text is None
