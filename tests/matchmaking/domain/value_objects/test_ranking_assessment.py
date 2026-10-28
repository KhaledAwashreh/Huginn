from dataclasses import FrozenInstanceError, replace
from datetime import datetime
from uuid import UUID

import pytest

from huginn.matchmaking.domain.value_objects.ranking_evidence import RankingEvidence
from huginn.matchmaking.domain.value_objects.ranking_restriction import (
    RankingRestriction,
)
from tests.matchmaking.domain.policies.test_research_scoring import assessment


def test_observation_identifiers_and_dates_are_strict():
    value = assessment().observations[0]
    for change in (
        {"observation_id": "bad"},
        {"description": " "},
        {"occurred_at": datetime(2026, 1, 1)},
        {"observed_at": False},
        {"source": ""},
        {"source_url": ""},
    ):
        with pytest.raises(ValueError):
            replace(value, **change)


def test_evidence_requires_a_valid_identifier_and_short_nonempty_quote():
    for identifier, quote in (
        ("bad", "valid"),
        (UUID(int=3), " "),
        (UUID(int=3), "word " * 26),
    ):
        with pytest.raises(ValueError):
            RankingEvidence(identifier, quote)


def test_assessment_is_deeply_immutable_and_rejects_mutable_inputs():
    value = assessment()
    with pytest.raises(FrozenInstanceError):
        value.rationale = "changed"
    with pytest.raises(ValueError):
        replace(value, observations=list(value.observations))
    with pytest.raises(ValueError):
        replace(value, unknowns=["mutable"])


def test_invalid_categories_ids_and_duplicate_observations_are_rejected():
    value = assessment()
    for changes in (
        {"company_id": "bad"},
        {"assessment_id": False},
        {"service_fit": "perfect"},
        {"business_context": "hiring"},
        {"service_basis": "certain"},
        {"size_match": True},
        {"observations": value.observations * 2},
        {"rationale": " "},
    ):
        with pytest.raises(ValueError):
            replace(value, **changes)


def test_quotes_references_and_relevant_timing_are_checked_against_full_sources():
    value = assessment()
    for changes in (
        {"evidence": (RankingEvidence(UUID(int=3), "invented quote"),)},
        {"evidence": (RankingEvidence(UUID(int=999), "source"),)},
        {"relevant_observation_ids": (UUID(int=999),)},
        {"timing_observation_id": UUID(int=999)},
    ):
        with pytest.raises(ValueError):
            replace(value, **changes)


def test_restriction_scopes_and_claims_require_exact_original_evidence():
    value = assessment()
    restriction = RankingRestriction(
        "advertised_job", "conflict", True, "Vacancy terms", value.evidence[0]
    )
    with pytest.raises(ValueError):
        replace(restriction, scope="whole_company")
    with pytest.raises(ValueError):
        replace(restriction, applies_to_hypothesis=1)
    with pytest.raises(ValueError):
        replace(
            value,
            restrictions=(
                replace(
                    restriction, evidence=RankingEvidence(UUID(int=3), "not stated")
                ),
            ),
        )
