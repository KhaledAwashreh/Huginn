"""Strict source-linked ranking operator input, docs/research-ranking.md."""

import json
from datetime import datetime
from uuid import UUID

from huginn.matchmaking.application.requests.research_ranking_request import (
    ResearchRankingRequest,
)
from huginn.matchmaking.domain.value_objects.ranking_assessment import RankingAssessment
from huginn.matchmaking.domain.value_objects.ranking_evidence import RankingEvidence
from huginn.matchmaking.domain.value_objects.ranking_observation import (
    RankingObservation,
)
from huginn.matchmaking.domain.value_objects.ranking_restriction import (
    RankingRestriction,
)


def _object(value, required, optional=()):
    if (
        type(value) is not dict
        or not set(required) <= set(value)
        or set(value) - set(required) - set(optional)
    ):
        raise ValueError("Unexpected or missing ranking fields")
    return value


def _array(value):
    if type(value) is not list:
        raise ValueError("Ranking collection must be an array")
    return value


def _identifier(value):
    if type(value) is not str:
        raise ValueError("Ranking identifier must be a UUID string")
    return UUID(value)


def _date(value, *, nullable=False):
    if value is None and nullable:
        return None
    if type(value) is not str:
        raise ValueError("Ranking date must be an ISO timestamp")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.utcoffset() is None:
        raise ValueError("Ranking date requires a timezone")
    return parsed


def _evidence(value):
    _object(value, ("observation_id", "quote"))
    return RankingEvidence(_identifier(value["observation_id"]), value["quote"])


def _observation(value):
    _object(
        value,
        (
            "observation_id",
            "description",
            "occurred_at",
            "observed_at",
            "source",
            "source_url",
        ),
    )
    return RankingObservation(
        _identifier(value["observation_id"]),
        value["description"],
        _date(value["occurred_at"], nullable=True),
        _date(value["observed_at"], nullable=True),
        value["source"],
        value["source_url"],
    )


def _restriction(value):
    _object(value, ("scope", "status", "applies_to_hypothesis", "reason", "evidence"))
    return RankingRestriction(
        value["scope"],
        value["status"],
        value["applies_to_hypothesis"],
        value["reason"],
        _evidence(value["evidence"]),
    )


def _assessment(value):
    required = (
        "company_id",
        "assessment_id",
        "service_fit",
        "business_context",
        "service_basis",
        "context_basis",
        "industry_match",
        "size_match",
        "country_match",
        "observations",
        "evidence",
        "relevant_observation_ids",
        "timing_observation_id",
        "unknowns",
        "rationale",
        "restrictions",
    )
    _object(value, required, ("semantic_service_logit", "semantic_model_reference"))
    return RankingAssessment(
        _identifier(value["company_id"]),
        _identifier(value["assessment_id"]),
        *(
            value[name]
            for name in (
                "service_fit",
                "business_context",
                "service_basis",
                "context_basis",
                "industry_match",
                "size_match",
                "country_match",
            )
        ),
        tuple(_observation(item) for item in _array(value["observations"])),
        tuple(_evidence(item) for item in _array(value["evidence"])),
        tuple(_identifier(item) for item in _array(value["relevant_observation_ids"])),
        None
        if value["timing_observation_id"] is None
        else _identifier(value["timing_observation_id"]),
        tuple(_array(value["unknowns"])),
        value["rationale"],
        tuple(_restriction(item) for item in _array(value["restrictions"])),
        value.get("semantic_service_logit"),
        value.get("semantic_model_reference"),
    )


def parse_ranking_input(value: object) -> ResearchRankingRequest:
    try:
        _object(
            value,
            (
                "schema_version",
                "profile_reference",
                "profile_snapshot",
                "assessment_method",
                "as_of",
                "limit",
                "seed",
                "assessments",
            ),
            ("semantic_query",),
        )
        if type(value["schema_version"]) is not int or value["schema_version"] != 1:
            raise ValueError("Unsupported ranking schema")
        if type(value["profile_snapshot"]) is not dict:
            raise ValueError("Profile snapshot must be an object")
        snapshot = json.dumps(
            value["profile_snapshot"],
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        )
        return ResearchRankingRequest(
            value["profile_reference"],
            snapshot,
            value["assessment_method"],
            _date(value["as_of"]),
            value["limit"],
            value["seed"],
            tuple(_assessment(a) for a in _array(value["assessments"])),
            value.get("semantic_query"),
        )
    except (TypeError, KeyError, AttributeError, OverflowError) as exc:
        raise ValueError("Invalid ranking input") from exc
