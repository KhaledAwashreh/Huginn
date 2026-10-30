"""Source-linked research relevance; no probability or buying-intent estimate."""

import math
from datetime import datetime, timedelta

from huginn.matchmaking.domain.constants.research_ranking import (
    CONTEXT_POINTS,
    RESEARCH_RANKING_VERSION,
    SERVICE_POINTS,
)
from huginn.matchmaking.domain.value_objects._ranking_validation import aware, require
from huginn.matchmaking.domain.value_objects.ranking_assessment import RankingAssessment
from huginn.matchmaking.domain.value_objects.ranking_score import RankingScore


def score_assessment(assessment: RankingAssessment, as_of: datetime) -> RankingScore:
    require(isinstance(assessment, RankingAssessment), "Ranking assessment required")
    aware(as_of, "as_of")
    referenced = {e.observation_id for e in assessment.evidence}
    referenced.update(r.evidence.observation_id for r in assessment.restrictions)
    observations = {o.observation_id: o for o in assessment.observations}
    for identifier in referenced:
        observation = observations[identifier]
        for value in (observation.occurred_at, observation.observed_at):
            require(
                value is None or value <= as_of, "Referenced source is in the future"
            )
    timing = 0
    if assessment.timing_observation_id is not None:
        when = observations[assessment.timing_observation_id].occurred_at
        if when is not None:
            age = as_of - when
            timing = next(
                (
                    points
                    for days, points in ((30, 15), (90, 12), (180, 9), (365, 6))
                    if age <= timedelta(days=days)
                ),
                3,
            )
    excluded = any(
        r.scope == "proposed_engagement"
        and r.status == "conflict"
        and r.applies_to_hypothesis
        for r in assessment.restrictions
    )
    unresolved = any(
        r.scope == "unknown"
        or r.status == "unknown"
        or (
            r.scope == "proposed_engagement"
            and r.status == "conflict"
            and not r.applies_to_hypothesis
        )
        for r in assessment.restrictions
    )
    disposition = (
        "excluded"
        if excluded
        else "unresolved"
        if unresolved
        else "not_applicable"
        if assessment.restrictions
        else "none"
    )
    bases = (assessment.service_basis, assessment.context_basis)
    confidence = (
        "low" if "unknown" in bases else "medium" if "inferred" in bases else "high"
    )
    service_points = SERVICE_POINTS[assessment.service_fit]
    if assessment.semantic_service_logit is not None:
        # Stable sigmoid; bounded relevance scaling, not a calibrated probability.
        value = assessment.semantic_service_logit
        if value >= 0:
            scaled = 1 / (1 + math.exp(-value))
        else:
            exponent = math.exp(value)
            scaled = exponent / (1 + exponent)
        service_points = round(40 * scaled)
    return RankingScore(
        assessment,
        RESEARCH_RANKING_VERSION,
        as_of,
        service_points,
        CONTEXT_POINTS[assessment.business_context],
        5
        * sum(
            value == "match"
            for value in (
                assessment.industry_match,
                assessment.size_match,
                assessment.country_match,
            )
        ),
        timing,
        confidence,
        excluded,
        disposition,
    )
