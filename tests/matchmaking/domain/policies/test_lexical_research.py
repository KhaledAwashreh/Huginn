from datetime import UTC, datetime, timedelta
from uuid import UUID

from huginn.matchmaking.domain.policies.lexical_research import (
    assess_topic_overlap,
    offering_terms,
)
from huginn.matchmaking.domain.value_objects.ranking_observation import (
    RankingObservation,
)

NOW = datetime(2026, 10, 28, tzinfo=UTC)


def observation(text, days=1, identity=1):
    return RankingObservation(
        UUID(int=identity),
        text,
        NOW - timedelta(days=days),
        NOW,
        "hn",
        "https://example.test/source",
    )


def test_offering_terms_are_distinct_bounded_and_ignore_generic_sales_words():
    assert offering_terms(
        "We provide consulting services to help your onboarding and onboarding teams"
    ) == ("onboarding",)
    assert len(offering_terms(" ".join("word" + str(i) for i in range(100)))) <= 24


def test_topic_overlap_is_grounded_low_confidence_and_never_asserts_internal_need():
    source = observation(
        "We sell onboarding software to customers. We are hiring full-time."
    )
    result = assess_topic_overlap(UUID(int=100), (source,), ("onboarding",), NOW)
    assert result.service_fit == "adjacent"
    assert result.service_basis == "inferred"
    assert result.business_context == "unknown"
    assert result.context_basis == "unknown"
    assert result.restrictions == ()
    assert result.evidence[0].quote in source.description
    assert len(result.evidence[0].quote.split()) <= 25
    assert "does not establish" in result.rationale


def test_no_substring_or_future_hits_and_timing_uses_only_matching_source():
    assert (
        assess_topic_overlap(
            UUID(int=100), (observation("We provide coaching"),), ("coach",), NOW
        )
        is None
    )
    assert (
        assess_topic_overlap(
            UUID(int=100), (observation("onboarding", days=-1),), ("onboarding",), NOW
        )
        is None
    )
    sources = (
        observation("onboarding", days=100),
        observation("unrelated news", identity=2),
        observation("onboarding", identity=3),
    )
    result = assess_topic_overlap(UUID(int=100), sources, ("onboarding",), NOW)
    assert result.timing_observation_id == UUID(int=3)
    assert result.relevant_observation_ids == (UUID(int=1), UUID(int=3))
    future = RankingObservation(
        UUID(int=4),
        "onboarding",
        NOW,
        NOW + timedelta(days=1),
        "hn",
        "https://example.test",
    )
    assert assess_topic_overlap(UUID(int=100), (future,), ("onboarding",), NOW) is None


def test_duplicate_mentions_cannot_raise_service_fit_and_full_source_is_preserved():
    text = " ".join(["onboarding"] * 100)
    result = assess_topic_overlap(
        UUID(int=100), (observation(text),), ("onboarding",), NOW
    )
    assert result.service_fit == "adjacent"
    assert result.observations[0].description == text
