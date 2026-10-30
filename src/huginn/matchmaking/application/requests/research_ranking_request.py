"""Immutable assessed-input batch, docs/research-ranking.md."""

import json
from dataclasses import dataclass
from datetime import datetime

from huginn.matchmaking.domain.value_objects.ranking_assessment import RankingAssessment


@dataclass(frozen=True)
class ResearchRankingRequest:
    profile_reference: str
    profile_snapshot_json: str
    assessment_method: str
    as_of: datetime
    limit: int
    seed: str
    assessments: tuple[RankingAssessment, ...]
    semantic_query: str | None = None

    def __post_init__(self) -> None:
        for name in ("profile_reference", "assessment_method", "seed"):
            value = getattr(self, name)
            if type(value) is not str or not value.strip() or len(value) > 500:
                raise ValueError("Invalid ranking envelope text")
        if not isinstance(self.as_of, datetime) or self.as_of.utcoffset() is None:
            raise ValueError("Ranking as_of must be timezone-aware")
        if type(self.limit) is not int or not 1 <= self.limit <= 100:
            raise ValueError("Ranking limit must be between 1 and 100")
        if type(self.profile_snapshot_json) is not str:
            raise ValueError("Profile snapshot must be immutable JSON text")
        profile = json.loads(self.profile_snapshot_json)
        if type(profile) is not dict or not profile:
            raise ValueError("A nonempty profile snapshot is required")
        json.dumps(profile, allow_nan=False)
        if (
            type(self.assessments) is not tuple
            or len(self.assessments) > 5000
            or not all(isinstance(a, RankingAssessment) for a in self.assessments)
        ):
            raise ValueError("Ranking assessments must be an immutable bounded tuple")
        ids = [a.assessment_id for a in self.assessments]
        if len(ids) != len(set(ids)):
            raise ValueError("Duplicate assessment identity")
        if self.semantic_query is not None and (
            type(self.semantic_query) is not str
            or not self.semantic_query.strip()
            or len(self.semantic_query) > 10000
        ):
            raise ValueError("Invalid semantic query")
        if self.semantic_query is None and any(
            assessment.semantic_service_logit is not None
            for assessment in self.assessments
        ):
            raise ValueError("Semantic snapshots require their original query")
