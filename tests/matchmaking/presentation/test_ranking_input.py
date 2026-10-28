from copy import deepcopy
from uuid import UUID

import pytest

from huginn.matchmaking.presentation.parsers.ranking_input import parse_ranking_input


def ranking_payload():
    observation_id = "00000000-0000-4000-8000-000000000001"
    return {
        "schema_version": 1,
        "profile_reference": "provider-example",
        "profile_snapshot": {"offering": "Customer onboarding process review"},
        "assessment_method": "source-linked operator assessment v1",
        "as_of": "2026-10-25T12:00:00Z",
        "limit": 5,
        "seed": "example-v1",
        "assessments": [
            {
                "company_id": "00000000-0000-4000-8000-000000000002",
                "assessment_id": "00000000-0000-4000-8000-000000000003",
                "service_fit": "direct",
                "business_context": "specific_context",
                "service_basis": "inferred",
                "context_basis": "observed",
                "industry_match": "match",
                "size_match": "unknown",
                "country_match": "match",
                "observations": [
                    {
                        "observation_id": observation_id,
                        "description": "Our first CS hire will build customer onboarding from scratch.",
                        "occurred_at": "2026-10-01T12:00:00Z",
                        "observed_at": "2026-10-24T12:00:00Z",
                        "source": "example",
                        "source_url": "https://example.invalid/company",
                    }
                ],
                "evidence": [
                    {
                        "observation_id": observation_id,
                        "quote": "build customer onboarding from scratch",
                    }
                ],
                "relevant_observation_ids": [observation_id],
                "timing_observation_id": observation_id,
                "unknowns": ["Independent project acceptance and budget"],
                "rationale": "An onboarding process review is a specific research hypothesis.",
                "restrictions": [],
            }
        ],
    }


def test_parser_produces_immutable_typed_source_linked_request():
    payload = ranking_payload()
    parsed = parse_ranking_input(payload)
    assert parsed is not None
    assert parsed.profile_reference == "provider-example"
    assert parsed.assessments[0].company_id == UUID(
        payload["assessments"][0]["company_id"]
    )
    payload["assessments"][0]["unknowns"].append("later edit")
    assert parsed.assessments[0].unknowns == (
        "Independent project acceptance and budget",
    )


@pytest.mark.parametrize(
    "field,value",
    [
        ("schema_version", True),
        ("limit", True),
        ("limit", 0),
        ("as_of", "2026-10-25"),
        ("seed", ""),
        ("assessment_method", ""),
        ("profile_snapshot", []),
        ("profile_snapshot", {"bad": float("nan")}),
    ],
)
def test_invalid_ranking_envelope_is_rejected(field, value):
    payload = ranking_payload()
    payload[field] = value
    with pytest.raises(ValueError):
        parse_ranking_input(payload)


def test_unknown_fields_and_forged_quotes_are_rejected():
    payload = ranking_payload()
    payload["unrecognized"] = "not silently ignored"
    with pytest.raises(ValueError):
        parse_ranking_input(payload)
    payload = ranking_payload()
    payload["assessments"][0]["evidence"][0]["quote"] = "a claim absent from the source"
    with pytest.raises(ValueError):
        parse_ranking_input(payload)


def test_nested_unknown_fields_and_missing_original_dates_are_rejected():
    payload = ranking_payload()
    payload["assessments"][0]["observations"][0]["new_field"] = True
    with pytest.raises(ValueError):
        parse_ranking_input(payload)
    payload = ranking_payload()
    del payload["assessments"][0]["observations"][0]["occurred_at"]
    with pytest.raises(ValueError):
        parse_ranking_input(payload)


def test_input_is_not_mutated():
    payload = ranking_payload()
    before = deepcopy(payload)
    parse_ranking_input(payload)
    assert payload == before
