from dataclasses import replace
from uuid import uuid4

import pytest

from huginn.matchmaking.application.services.research_ranking_service import (
    ResearchRankingService,
)


def request_value():
    from datetime import UTC, datetime

    from huginn.matchmaking.application.requests.research_ranking_request import (
        ResearchRankingRequest,
    )
    from huginn.matchmaking.domain.value_objects.ranking_assessment import (
        RankingAssessment,
    )
    from huginn.matchmaking.domain.value_objects.ranking_evidence import RankingEvidence
    from huginn.matchmaking.domain.value_objects.ranking_observation import (
        RankingObservation,
    )

    observation = RankingObservation(
        uuid4(),
        "We are building onboarding from scratch.",
        datetime(2026, 10, 1, tzinfo=UTC),
        datetime(2026, 10, 24, tzinfo=UTC),
        "example",
        "https://example.invalid",
    )
    candidate = RankingAssessment(
        uuid4(),
        uuid4(),
        "direct",
        "specific_context",
        "inferred",
        "observed",
        "match",
        "unknown",
        "match",
        (observation,),
        (
            RankingEvidence(
                observation.observation_id, "building onboarding from scratch"
            ),
        ),
        (observation.observation_id,),
        observation.observation_id,
        ("Budget and independent-project acceptance",),
        "A source-grounded process research hypothesis.",
    )
    return ResearchRankingRequest(
        "test-provider",
        '{"offering":"onboarding"}',
        "operator-v1",
        datetime(2026, 10, 25, tzinfo=UTC),
        5,
        "fixed-seed",
        (candidate,),
    )


def test_ranking_service_produces_stable_snapshot_and_breakdown():
    request = request_value()
    response = ResearchRankingService().execute(request)
    assert response is not None
    assert len(response.ranking_id) == 64
    assert response.scores[0].total == 85
    assert response.scores[0].confidence == "medium"
    assert response.selection.candidates[0].score.assessment == request.assessments[0]
    assert ResearchRankingService().execute(request) == response


def test_snapshot_identity_changes_with_source_or_profile_or_selection_seed():
    request = request_value()
    baseline = ResearchRankingService().execute(request)
    assert baseline is not None
    for changed in (
        replace(request, seed="different"),
        replace(request, profile_snapshot_json='{"offering":"different"}'),
        replace(
            request,
            assessments=(
                replace(request.assessments[0], rationale="Revised inference"),
            ),
        ),
    ):
        assert (
            ResearchRankingService().execute(changed).ranking_id != baseline.ranking_id
        )


def test_snapshot_is_independent_of_assessment_input_order():
    request = request_value()
    second = replace(request.assessments[0], company_id=uuid4(), assessment_id=uuid4())
    a = ResearchRankingService().execute(
        replace(request, assessments=(*request.assessments, second))
    )
    b = ResearchRankingService().execute(
        replace(request, assessments=(second, *request.assessments))
    )
    assert a is not None
    assert a == b


def test_invalid_request_and_unconfigured_semantic_assessment_fail():
    with pytest.raises(ValueError):
        ResearchRankingService().execute(None)
    with pytest.raises(ValueError):
        ResearchRankingService().execute(
            replace(request_value(), semantic_query="Need a semantic model")
        )


def test_json_parser_preserves_precomputed_semantic_values_for_replay():
    # A semantic snapshot can be replayed without importing or invoking an ML runtime.
    request = request_value()
    assessment = replace(
        request.assessments[0],
        semantic_service_logit=0.0,
        semantic_model_reference="test-model/raw-logit-v1",
    )
    response = ResearchRankingService().execute(
        replace(request, assessments=(assessment,), semantic_query="Onboarding process")
    )
    assert response is not None
    assert response.scores[0].service_points == 20
    assert response.scores[0].service_scoring_mode == "semantic_logit"


def test_semantic_service_uses_complete_asof_context_and_replays_exactly():
    from datetime import timedelta

    from huginn.matchmaking.application.read_models.semantic_relevance import (
        SemanticRelevance,
    )
    from huginn.matchmaking.application.serializers.research_ranking import (
        serialize_research_ranking,
    )
    from huginn.matchmaking.presentation.parsers.ranking_input import (
        parse_ranking_input,
    )

    request = request_value()
    original = request.assessments[0]
    future = replace(
        original.observations[0],
        observation_id=uuid4(),
        description="Future context",
        occurred_at=request.as_of + timedelta(days=1),
    )
    request = replace(
        request,
        assessments=(replace(original, observations=(*original.observations, future)),),
        semantic_query="Onboarding consulting",
    )

    class Reranker:
        def rerank(self, query, documents):
            assert query == request.semantic_query
            assert documents == (original.observations[0].description,)
            return SemanticRelevance((0.0,), "test-model")

    output = serialize_research_ranking(
        ResearchRankingService(Reranker()).execute(request)
    )
    assert output["recommendations"][0]["breakdown"]["service_fit"] == 20
    assert len(output["input_snapshot"]["assessments"][0]["observations"]) == 2
    assert (
        serialize_research_ranking(
            ResearchRankingService().execute(
                parse_ranking_input(output["input_snapshot"])
            )
        )
        == output
    )


def test_semantic_service_rejects_wrong_result_count_and_snapshot_overwrite():
    from huginn.matchmaking.application.read_models.semantic_relevance import (
        SemanticRelevance,
    )

    request = replace(request_value(), semantic_query="Onboarding consulting")

    class Reranker:
        def rerank(self, query, documents):
            return SemanticRelevance((), "test-model")

    with pytest.raises(ValueError, match="count"):
        ResearchRankingService(Reranker()).execute(request)
    scored = replace(
        request.assessments[0],
        semantic_service_logit=0.0,
        semantic_model_reference="previous-model",
    )
    with pytest.raises(ValueError, match="replace"):
        ResearchRankingService(Reranker()).execute(
            replace(request, assessments=(scored,))
        )


def test_semantic_snapshot_requires_original_query():
    request = request_value()
    scored = replace(
        request.assessments[0],
        semantic_service_logit=0.0,
        semantic_model_reference="previous-model",
    )
    with pytest.raises(ValueError, match="query"):
        replace(request, assessments=(scored,))
