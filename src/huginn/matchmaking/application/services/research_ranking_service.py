"""Versioned assessed-input research ranking, docs/research-ranking.md."""

import hashlib
import json
import logging
from dataclasses import asdict, replace
from datetime import UTC, datetime
from uuid import UUID

from huginn.matchmaking.application.protocols.semantic_reranker import SemanticReranker
from huginn.matchmaking.application.requests.research_ranking_request import (
    ResearchRankingRequest,
)
from huginn.matchmaking.application.responses.research_ranking_response import (
    ResearchRankingResponse,
)
from huginn.matchmaking.domain.constants.research_ranking import (
    RESEARCH_RANKING_VERSION,
)
from huginn.matchmaking.domain.policies.research_scoring import score_assessment
from huginn.matchmaking.domain.policies.research_selection import (
    select_research_candidates,
)

logger = logging.getLogger(__name__)


def _canonical(value):
    if isinstance(value, datetime):
        return value.astimezone(UTC).isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _canonical(item) for key, item in value.items()}
    if isinstance(value, (tuple, list)):
        return [_canonical(item) for item in value]
    return value


def _semantic_document(assessment, as_of):
    eligible = [
        observation
        for observation in assessment.observations
        if all(
            value is None or value <= as_of
            for value in (observation.occurred_at, observation.observed_at)
        )
    ]
    if not eligible:
        raise ValueError("No as-of source context available for semantic ranking")
    return "\n\n".join(
        observation.description
        for observation in sorted(
            eligible, key=lambda observation: observation.observation_id
        )
    )


class ResearchRankingService:
    def __init__(self, semantic_reranker: SemanticReranker | None = None):
        self._reranker = semantic_reranker

    def execute(self, request: ResearchRankingRequest) -> ResearchRankingResponse:
        if not isinstance(request, ResearchRankingRequest):
            raise ValueError("Research ranking request required")
        logger.info(
            "Research ranking started for %s assessed candidates",
            len(request.assessments),
        )
        assessments = tuple(
            sorted(request.assessments, key=lambda assessment: assessment.assessment_id)
        )
        initial = tuple(
            score_assessment(assessment, request.as_of) for assessment in assessments
        )
        eligible = [index for index, score in enumerate(initial) if not score.excluded]
        if self._reranker is not None:
            if request.semantic_query is None:
                raise ValueError("An explicit semantic query is required")
            if any(
                assessments[index].semantic_service_logit is not None
                for index in eligible
            ):
                raise ValueError(
                    "Cannot silently replace a precomputed semantic snapshot"
                )
            if eligible:
                result = self._reranker.rerank(
                    request.semantic_query,
                    tuple(
                        _semantic_document(assessments[index], request.as_of)
                        for index in eligible
                    ),
                )
                if len(result.logits) != len(eligible):
                    raise ValueError(
                        "Semantic score count differs from candidate count"
                    )
                updated = list(assessments)
                for index, logit in zip(eligible, result.logits, strict=True):
                    updated[index] = replace(
                        assessments[index],
                        semantic_service_logit=logit,
                        semantic_model_reference=result.model_reference,
                    )
                assessments = tuple(updated)
        elif request.semantic_query is not None and any(
            assessments[index].semantic_service_logit is None for index in eligible
        ):
            raise ValueError(
                "Configure a semantic reranker or provide precomputed semantic scores"
            )
        request = replace(
            request,
            assessments=assessments,
            profile_snapshot_json=json.dumps(
                json.loads(request.profile_snapshot_json),
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ),
        )
        scores = tuple(
            score_assessment(assessment, request.as_of)
            for assessment in request.assessments
        )
        selection = select_research_candidates(scores, request.limit, request.seed)
        values = _canonical(asdict(request))
        input_fingerprint = hashlib.sha256(
            json.dumps(
                values, sort_keys=True, separators=(",", ":"), allow_nan=False
            ).encode()
        ).hexdigest()
        ranking_id = hashlib.sha256(
            (RESEARCH_RANKING_VERSION + "/" + input_fingerprint).encode()
        ).hexdigest()
        logger.info(
            "Research ranking completed with %s selected and %s exploratory",
            len(selection.candidates),
            selection.actual_exploration_slots,
        )
        return ResearchRankingResponse(
            ranking_id, input_fingerprint, request, scores, selection
        )
