from dataclasses import replace

import pytest

from huginn.matchmaking.domain.policies.research_scoring import score_assessment
from tests.matchmaking.domain.policies.test_research_scoring import AS_OF, assessment


def test_semantic_logit_zero_is_twenty_relevance_points_not_a_probability():
    value = replace(
        assessment(),
        semantic_service_logit=0.0,
        semantic_model_reference="model@revision",
    )
    result = score_assessment(value, AS_OF)
    assert result.service_points == 20
    assert result.service_scoring_mode == "semantic_logit"
    assert result.confidence == "high"
    assert result.assessment.service_fit == "direct"


def test_extreme_logits_are_stable_monotonic_and_capped():
    points = []
    for logit in (-1000, -10, -1, 0, 1, 10, 1000):
        value = replace(
            assessment(),
            semantic_service_logit=logit,
            semantic_model_reference="model@revision",
        )
        points.append(score_assessment(value, AS_OF).service_points)
    assert points == sorted(points)
    assert points[0] == 0
    assert points[-1] == 40


def test_semantic_input_pair_rejects_invalid_logits_and_model_references():
    for logit in (True, "1", float("inf"), float("-inf"), float("nan"), 10**1000):
        with pytest.raises(ValueError):
            replace(
                assessment(),
                semantic_service_logit=logit,
                semantic_model_reference="model",
            )
    for reference in (None, "", " ", "m" * 257, 7):
        with pytest.raises(ValueError):
            replace(
                assessment(),
                semantic_service_logit=0.0,
                semantic_model_reference=reference,
            )
    with pytest.raises(ValueError):
        replace(assessment(), semantic_model_reference="model")


def test_label_mode_remains_default_and_confidence_is_independent_of_logit():
    assert (
        score_assessment(assessment(), AS_OF).service_scoring_mode == "assessed_label"
    )
    value = replace(
        assessment(),
        service_basis="unknown",
        semantic_service_logit=1000.0,
        semantic_model_reference="model",
    )
    result = score_assessment(value, AS_OF)
    assert result.service_points == 40
    assert result.confidence == "low"
