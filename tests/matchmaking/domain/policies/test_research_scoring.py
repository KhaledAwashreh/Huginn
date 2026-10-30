from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from huginn.matchmaking.domain.policies.research_scoring import score_assessment
from huginn.matchmaking.domain.value_objects.ranking_assessment import RankingAssessment
from huginn.matchmaking.domain.value_objects.ranking_evidence import RankingEvidence
from huginn.matchmaking.domain.value_objects.ranking_observation import (
    RankingObservation,
)
from huginn.matchmaking.domain.value_objects.ranking_restriction import (
    RankingRestriction,
)

AS_OF = datetime(2026, 10, 25, tzinfo=UTC)


def assessment(**changes):
    observation = RankingObservation(
        UUID(int=3),
        "We are building our first customer success function.",
        AS_OF - timedelta(days=10),
        AS_OF,
        "hn",
        "https://example.invalid/source",
    )
    value = RankingAssessment(
        UUID(int=1),
        UUID(int=2),
        "direct",
        "explicit_change",
        "observed",
        "observed",
        "match",
        "match",
        "match",
        (observation,),
        (
            RankingEvidence(
                observation.observation_id, "first customer success function"
            ),
        ),
        (observation.observation_id,),
        observation.observation_id,
        ("Budget and acceptance remain unknown",),
        "Research the named onboarding function.",
    )
    return replace(value, **changes)


def test_fixed_feature_caps_sum_to_one_hundred():
    result = score_assessment(assessment(), AS_OF)
    assert result is not None, "Scoring must return an explainable result"
    assert (
        result.service_points,
        result.context_points,
        result.preference_points,
        result.timing_points,
    ) == (40, 30, 15, 15)
    assert result.total == 100
    assert result.version == "research-ranking-v1"
    assert result.assessment == assessment()


def test_confidence_is_separate_from_relevance_and_unknown_preferences_do_not_block():
    value = assessment(
        service_basis="unknown",
        context_basis="inferred",
        industry_match="unknown",
        size_match="unknown",
        country_match="unknown",
    )
    result = score_assessment(value, AS_OF)
    assert result is not None
    assert result.total == 85
    assert result.confidence == "low"
    assert result.excluded is False
    assert result.assessment.unknowns == value.unknowns


def test_inferred_evidence_has_medium_confidence_without_reducing_feature_points():
    result = score_assessment(assessment(service_basis="inferred"), AS_OF)
    assert result is not None
    assert result.total == 100
    assert result.confidence == "medium"


def test_service_and_context_categories_score_once_not_per_quote_or_observation():
    value = assessment(service_fit="plausible", business_context="specific_context")
    duplicate_claim = replace(value.observations[0], observation_id=UUID(int=4))
    expanded = replace(
        value,
        observations=value.observations + (duplicate_claim,),
        evidence=value.evidence
        + (RankingEvidence(UUID(int=4), "first customer success function"),),
        relevant_observation_ids=(UUID(int=3), UUID(int=4)),
    )
    one = score_assessment(value, AS_OF)
    many = score_assessment(expanded, AS_OF)
    assert one is not None and many is not None
    assert one.total == many.total == 78


def test_timing_uses_only_the_explicit_relevant_source_event():
    value = assessment()
    old = replace(value.observations[0], occurred_at=AS_OF - timedelta(days=500))
    unrelated = replace(
        value.observations[0],
        observation_id=UUID(int=4),
        description="New unrelated product announcement",
        occurred_at=AS_OF,
    )
    result = score_assessment(replace(value, observations=(old, unrelated)), AS_OF)
    assert result is not None
    assert result.timing_points == 3


def test_timing_boundaries_and_undated_context():
    for days, points in (
        (0, 15),
        (30, 15),
        (31, 12),
        (90, 12),
        (91, 9),
        (180, 9),
        (181, 6),
        (365, 6),
        (366, 3),
    ):
        value = assessment()
        result = score_assessment(
            replace(
                value,
                observations=(
                    replace(
                        value.observations[0], occurred_at=AS_OF - timedelta(days=days)
                    ),
                ),
            ),
            AS_OF,
        )
        assert result is not None
        assert result.timing_points == points
    value = assessment()
    result = score_assessment(
        replace(
            value, observations=(replace(value.observations[0], occurred_at=None),)
        ),
        AS_OF,
    )
    assert result is not None
    assert result.timing_points == 0


def test_vacancy_and_contact_restrictions_never_block_the_company_hypothesis():
    for scope in ("advertised_job", "contact_route", "unknown"):
        value = assessment()
        restriction = RankingRestriction(
            scope, "conflict", True, "The vacancy is full-time", value.evidence[0]
        )
        result = score_assessment(replace(value, restrictions=(restriction,)), AS_OF)
        assert result is not None
        assert result.excluded is False


def test_only_an_explicit_applicable_engagement_conflict_excludes():
    value = assessment()
    restriction = RankingRestriction(
        "proposed_engagement",
        "conflict",
        True,
        "The proposed work must be onsite",
        value.evidence[0],
    )
    result = score_assessment(replace(value, restrictions=(restriction,)), AS_OF)
    assert result is not None
    assert result.excluded is True
    assert result.restriction_disposition == "excluded"
    not_applicable = score_assessment(
        replace(
            value, restrictions=(replace(restriction, applies_to_hypothesis=False),)
        ),
        AS_OF,
    )
    assert not_applicable is not None
    assert not_applicable.excluded is False


def test_future_referenced_events_and_observation_availability_are_rejected():
    value = assessment()
    for field in ("occurred_at", "observed_at"):
        future = replace(value.observations[0], **{field: AS_OF + timedelta(seconds=1)})
        with pytest.raises(ValueError, match="future"):
            score_assessment(replace(value, observations=(future,)), AS_OF)
    with pytest.raises(ValueError, match="timezone"):
        score_assessment(value, datetime(2026, 10, 25))


def test_uncited_future_observation_cannot_boost_or_invalidate_a_score():
    value = assessment()
    future = replace(
        value.observations[0],
        observation_id=UUID(int=10),
        occurred_at=AS_OF + timedelta(days=5),
        observed_at=AS_OF + timedelta(days=5),
    )
    result = score_assessment(
        replace(value, observations=value.observations + (future,)), AS_OF
    )
    assert result is not None
    assert result.total == 100
