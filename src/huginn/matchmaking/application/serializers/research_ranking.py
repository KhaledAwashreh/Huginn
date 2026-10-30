"""Complete immutable ranking snapshots for operator review and later feedback."""

import hashlib
import json
from dataclasses import asdict
from datetime import UTC, datetime
from uuid import UUID

from huginn.matchmaking.application.responses.research_ranking_response import (
    ResearchRankingResponse,
)
from huginn.matchmaking.domain.constants.research_ranking import (
    SEMANTIC_SERVICE_TRANSFORM,
)


def _plain(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_plain(item) for item in value]
    return value


def _score(value):
    assessment = value.assessment
    return {
        "company_id": str(assessment.company_id),
        "assessment_id": str(assessment.assessment_id),
        "score": value.total,
        "confidence": value.confidence,
        "breakdown": {
            "service_fit": value.service_points,
            "business_context": value.context_points,
            "company_preferences": value.preference_points,
            "timing": value.timing_points,
        },
        "service_scoring_mode": value.service_scoring_mode,
        "semantic_service_logit": assessment.semantic_service_logit,
        "semantic_model_reference": assessment.semantic_model_reference,
        "semantic_transform": SEMANTIC_SERVICE_TRANSFORM
        if assessment.semantic_service_logit is not None
        else None,
        "excluded": value.excluded,
        "restriction_disposition": value.restriction_disposition,
        "relevant_observation_ids": [
            str(value) for value in assessment.relevant_observation_ids
        ],
        "timing_observation_id": None
        if assessment.timing_observation_id is None
        else str(assessment.timing_observation_id),
        "evidence": _plain([asdict(evidence) for evidence in assessment.evidence]),
        "unknowns": list(assessment.unknowns),
        "rationale": assessment.rationale,
    }


def serialize_research_ranking(response: ResearchRankingResponse) -> dict:
    request = _plain(asdict(response.request))
    request["profile_snapshot"] = json.loads(request.pop("profile_snapshot_json"))
    request["schema_version"] = 1
    recommendations = []
    for position, selected in enumerate(response.selection.candidates, 1):
        score = selected.score
        identity = f"{response.ranking_id}/{score.assessment.company_id}/{score.assessment.assessment_id}/{position}"
        recommendations.append(
            {
                "recommendation_id": hashlib.sha256(identity.encode()).hexdigest(),
                "position": position,
                "selection_type": selected.selection_type,
                **_score(score),
            }
        )
    return {
        "schema_version": 1,
        "algorithm_version": response.selection.version,
        "ranking_id": response.ranking_id,
        "input_fingerprint": response.input_fingerprint,
        "mode": "assessed-input-research-ranking",
        "score_is_probability": False,
        "confidence_meaning": "Evidence basis for relevance, not probability of buying or verification of source truth",
        "weights": {
            "service_fit": 40,
            "business_context": 30,
            "company_preferences": 15,
            "timing": 15,
        },
        "requested": response.selection.limit,
        "displayed": len(recommendations),
        "requested_exploration_slots": response.selection.requested_exploration_slots,
        "actual_exploration_slots": response.selection.actual_exploration_slots,
        "excluded_company_ids": [
            str(value) for value in response.selection.excluded_company_ids
        ],
        "recommendations": recommendations,
        "scored_candidates": [_score(value) for value in response.scores],
        "input_snapshot": request,
    }
