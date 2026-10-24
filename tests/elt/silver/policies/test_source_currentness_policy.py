from datetime import UTC, datetime

import pytest

from huginn.elt.silver.models.lifecycle_input import LifecycleInput
from huginn.elt.silver.models.source_extraction import SourceExtraction
from huginn.elt.silver.policies.source_currentness import classify


def _item(
    source: str,
    payload: object,
    *,
    stable_id: str | None = None,
    resolved_company_key: str | None = None,
    key_derivation: str | None = None,
) -> LifecycleInput:
    return LifecycleInput(
        source=source,  # type: ignore[arg-type]
        stable_id=stable_id or str(payload.get("id", "acme"))
        if isinstance(payload, dict)
        else stable_id or "invalid",
        payload=payload,  # type: ignore[arg-type]
        raw_token="raw-v1",
        resolution_token="resolution-v1",
        resolved_company_key=resolved_company_key,
        key_derivation=key_derivation,
        company_id=None,
        fetched_at=datetime(2026, 10, 1, tzinfo=UTC),
        last_checked_at=datetime(2026, 10, 2, tzinfo=UTC),
    )


def test_yc_explicit_false_hiring_is_distinct_from_missing():
    false = classify(
        _item("yc", {"id": 1, "slug": "acme", "status": "Active", "isHiring": False})
    )
    unknown = classify(_item("yc", {"id": 2, "slug": "beta", "status": "Active"}))

    assert false.hiring_state == "false"
    assert unknown.hiring_state == "unknown"


def test_yc_closed_status_with_malformed_context_fields_still_withdraws():
    facts = classify(
        _item(
            "yc",
            {
                "id": 17,
                "status": "Acquired",
                "slug": None,
                "launched_at": 1_700_000_000,
            },
        )
    )

    assert facts.listing_state == "withdrawn"
    assert facts.hiring_state == "unknown"
    assert facts.occurred_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


def test_yc_malformed_description_keeps_independently_valid_launch_time():
    facts = classify(
        _item(
            "yc",
            {
                "id": 18,
                "slug": "acme",
                "status": "Active",
                "long_description": 17,
                "launched_at": 1_700_000_000,
            },
        )
    )

    assert facts.listing_state == "invalid"
    assert facts.occurred_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


def test_yc_requires_matching_raw_id_and_preserves_bounded_launch_time():
    payload = {
        "id": 12,
        "slug": "acme",
        "status": "Public",
        "launched_at": 1_700_000_000,
    }
    wrong_id = classify(
        _item(
            "yc",
            {**payload, "isHiring": False},
            stable_id="13",
        )
    )
    matching = classify(_item("yc", payload, stable_id="12"))

    assert wrong_id.listing_state == "invalid"
    assert wrong_id.hiring_state == "false"
    assert matching.listing_state == "available"
    assert matching.occurred_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


def test_yc_stable_id_comparison_does_not_strip_item_id():
    facts = classify(
        _item(
            "yc",
            {"id": 12, "slug": "acme", "status": "Active"},
            stable_id=" 12 ",
        )
    )

    assert facts.listing_state == "invalid"


def test_hn_deleted_with_bad_timestamp_withdraws_without_context_failure():
    facts = classify(
        _item("hn", {"id": 44, "type": "comment", "deleted": True, "time": "bad"})
    )

    assert facts.listing_state == "withdrawn"
    assert facts.hiring_state == "true"


def test_hn_valid_time_survives_unrelated_context_failure():
    facts = classify(
        _item(
            "hn",
            {"id": 48, "type": "comment", "text": 17, "time": 1_700_000_000},
        )
    )

    assert facts.listing_state == "invalid"
    assert facts.occurred_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)


def test_hn_empty_comment_with_bad_timestamp_withdraws():
    facts = classify(
        _item("hn", {"id": 47, "type": "comment", "text": "", "time": "bad"})
    )

    assert facts.listing_state == "withdrawn"


def test_hn_body_link_is_not_explicit_company_identity():
    facts = classify(
        _item(
            "hn",
            {
                "id": 45,
                "type": "comment",
                "time": 1_700_000_000,
                "text": 'Acme | Remote<p>See <a href="https://body.example">our site</a>',
            },
        )
    )

    assert facts.listing_state == "available"
    assert facts.explicit_domain is None
    assert facts.identity_state == "missing"


def test_identity_domain_change_is_a_mismatch_against_current_resolution():
    facts = classify(
        _item(
            "yc",
            {
                "id": 9,
                "slug": "acme",
                "status": "Active",
                "website": "https://new.example/jobs",
            },
            resolved_company_key="old.example",
            key_derivation="domain_normalized",
        )
    )

    assert facts.explicit_domain == "new.example"
    assert facts.identity_state == "mismatch"


def test_identity_requires_domain_normalized_resolution_and_normalized_equality():
    unresolved = classify(
        _item(
            "yc",
            {"id": 10, "slug": "acme", "status": "Active", "website": "acme.example"},
            resolved_company_key="acme.example",
            key_derivation="fuzzy_matched",
        )
    )
    consistent = classify(
        _item(
            "yc",
            {
                "id": 11,
                "slug": "beta",
                "status": "Active",
                "website": "https://www.acme.example/",
            },
            resolved_company_key="acme.example",
            key_derivation="domain_normalized",
        )
    )

    assert unresolved.identity_state == "unresolved"
    assert consistent.identity_state == "consistent"


def test_eu_captured_listing_is_available_and_keeps_freeform_status():
    payload = {
        "url": "https://www.eu-startups.com/directory/acme/",
        "lastmod": "2026-09-30T12:30:00+02:00",
        "html": """<div class="wpbdp-listing-single"><h2 class="listing-title">Acme</h2>
        <div class="wpbdp-field-company_status"><div class="value">Maybe closed soon</div></div>
        <div class="wpbdp-field-website"><div class="value"><a href="https://acme.example">Acme</a></div></div>
        </div>""",
    }
    facts = classify(_item("eu_startups", payload))

    assert facts.listing_state == "available"
    assert facts.context.source_fields["status"] == "Maybe closed soon"
    assert facts.explicit_domain == "acme.example"
    assert facts.occurred_at == datetime.fromisoformat("2026-09-30T12:30:00+02:00")


def test_eu_unrecognized_status_does_not_change_captured_listing_lifecycle():
    payload = {
        "url": "https://www.eu-startups.com/directory/acme/",
        "html": """<div class="wpbdp-listing-single"><h2 class="listing-title">Acme</h2>
        <div class="wpbdp-field-company_status"><div class="value">Closed</div></div>
        </div>""",
    }

    assert classify(_item("eu_startups", payload)).listing_state == "available"


def test_eu_valid_lastmod_survives_invalid_listing_context():
    facts = classify(
        _item(
            "eu_startups",
            {
                "url": "https://www.eu-startups.com/directory/acme/",
                "lastmod": "2026-09-30T12:30:00+02:00",
                "html": "not a listing",
            },
        )
    )

    assert facts.listing_state == "invalid"
    assert facts.occurred_at == datetime.fromisoformat("2026-09-30T12:30:00+02:00")


def test_malformed_source_timestamp_never_falls_back_to_fetch_time():
    facts = classify(
        _item(
            "yc", {"id": 21, "slug": "acme", "status": "Active", "launched_at": 1e100}
        )
    )

    assert facts.occurred_at is None
    assert facts.occurred_at != datetime(2026, 10, 1, tzinfo=UTC)


def test_identity_rejects_credentials_and_mailto_urls():
    for website in ("https://user:pass@acme.example", "mailto:hello@acme.example"):
        facts = classify(
            _item(
                "yc",
                {"id": 31, "slug": "acme", "status": "Active", "website": website},
                resolved_company_key="acme.example",
                key_derivation="domain_normalized",
            )
        )
        assert facts.explicit_domain is None
        assert facts.identity_state == "missing"


def test_hn_header_link_is_the_only_hn_identity_candidate():
    facts = classify(
        _item(
            "hn",
            {
                "id": 46,
                "type": "comment",
                "time": 1_700_000_000,
                "text": 'Acme <a href="https://www.acme.example/jobs">site</a><p>Body',
            },
            resolved_company_key="acme.example",
            key_derivation="domain_normalized",
        )
    )

    assert facts.explicit_domain == "acme.example"
    assert facts.identity_state == "consistent"


def test_hn_paragraph_attributes_end_the_header_before_body_links():
    facts = classify(
        _item(
            "hn",
            {
                "id": 49,
                "type": "comment",
                "time": 1_700_000_000,
                "text": 'Acme | Remote<p class="body">Body <a href="https://body.example">site</a>',
            },
        )
    )

    assert facts.listing_state == "available"
    assert facts.explicit_domain is None


@pytest.mark.parametrize("source", ["hn", "yc", "eu_startups"])
@pytest.mark.parametrize("payload", [None, [], "raw", True])
def test_non_object_bronze_payload_is_classified_invalid(source, payload):
    facts = classify(_item(source, payload))

    assert facts.listing_state == "invalid"
    assert facts.hiring_state == (
        "unknown" if source in {"hn", "yc"} else "not_applicable"
    )
    assert facts.identity_state == "missing"
    assert facts.reason == "malformed_payload"
    assert facts.explicit_domain is None
    assert facts.occurred_at is None
    assert facts.context == SourceExtraction(
        source=source,
        stable_id=None,
        status="failed",
        reason="malformed_payload",
    )


@pytest.mark.parametrize(
    "status",
    [
        "CLOSED NOW",
        "CLOSED NOW - role filled",
        "closed now: role filled",
        "CLOSED NOW!",
    ],
)
def test_explicit_hn_header_closure_withdraws_listing_and_retains_context(status):
    payload = {
        "id": 50,
        "type": "comment",
        "time": 1_700_000_000,
        "text": f"Acme | Product Engineer | Freelance / employment | {status}<p>We are reviewing applications on a rolling basis.",
    }
    facts = classify(_item("hn", payload))
    assert facts.listing_state == "withdrawn"
    assert facts.reason == "hn_explicit_header_closed"
    assert facts.hiring_state == "true"
    assert facts.occurred_at == datetime(2023, 11, 14, 22, 13, 20, tzinfo=UTC)
    assert status in facts.context.normalized_text
    assert "reviewing applications" in facts.context.normalized_text
    assert facts.context.status == "captured"


@pytest.mark.parametrize(
    "text",
    [
        "Acme | Remote<p>CLOSED NOW - our old office, not this role.",
        "Acme | NOT CLOSED NOW<p>Apply here.",
        "Acme | Closed-source engineer<p>Apply here.",
        "Acme | https://example.test/closed-now<p>Apply here.",
        "Closed Now Labs | Remote<p>Apply here.",
        "Acme | Our funding round closed now<p>Apply here.",
    ],
)
def test_hn_closure_words_without_explicit_header_status_stay_available(text):
    facts = classify(_item("hn", {"id": 51, "type": "comment", "text": text}))
    assert facts.listing_state == "available"
