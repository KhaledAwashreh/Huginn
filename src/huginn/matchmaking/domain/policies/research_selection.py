"""Deterministic source-preserving ranking with bounded uncertain-tail exploration."""

import hashlib

from huginn.matchmaking.domain.constants.research_ranking import (
    CONFIDENCE_ORDER,
    RESEARCH_RANKING_VERSION,
)
from huginn.matchmaking.domain.value_objects._ranking_validation import require, text
from huginn.matchmaking.domain.value_objects.ranked_candidate import RankedCandidate
from huginn.matchmaking.domain.value_objects.ranking_score import RankingScore
from huginn.matchmaking.domain.value_objects.ranking_selection import RankingSelection


def select_research_candidates(
    scores: tuple[RankingScore, ...], limit: int, seed: str
) -> RankingSelection:
    require(
        type(scores) is tuple and all(isinstance(s, RankingScore) for s in scores),
        "Scores must be an immutable typed tuple",
    )
    require(type(limit) is int and 1 <= limit <= 100, "Limit must be between 1 and 100")
    text(seed, "Selection seed")
    assessment_ids = tuple(s.assessment.assessment_id for s in scores)
    require(
        len(set(assessment_ids)) == len(assessment_ids),
        "Duplicate assessment identifier",
    )
    require(len({s.as_of for s in scores}) <= 1, "Scores must share an as_of timestamp")
    require(
        all(s.version == RESEARCH_RANKING_VERSION for s in scores),
        "Cannot mix scoring versions",
    )

    def order(score: RankingScore):
        return (
            -score.total,
            CONFIDENCE_ORDER[score.confidence],
            score.assessment.company_id,
            score.assessment.assessment_id,
        )

    by_company = {}
    for score in sorted((s for s in scores if not s.excluded), key=order):
        by_company.setdefault(score.assessment.company_id, score)
    ordered = sorted(by_company.values(), key=order)
    excluded = tuple(
        sorted({s.assessment.company_id for s in scores} - by_company.keys())
    )
    capacity = min(limit, len(ordered))
    target = capacity // 5
    head_count = capacity - target
    tail = ordered[head_count:]
    exploratory = sorted(
        (
            s
            for s in tail
            if s.confidence != "high"
            and s.assessment.service_fit in ("direct", "plausible", "adjacent")
        ),
        key=lambda s: (
            hashlib.sha256(
                f"{RESEARCH_RANKING_VERSION}/{seed}/{s.assessment.assessment_id}".encode()
            ).hexdigest(),
            s.assessment.company_id,
        ),
    )[:target]
    exploratory_ids = {s.assessment.company_id for s in exploratory}
    ordinary = [s for s in ordered if s.assessment.company_id not in exploratory_ids][
        : capacity - len(exploratory)
    ]
    candidates = []
    ordinary_index = exploration_index = 0
    for position in range(1, capacity + 1):
        use_exploration = exploration_index < len(exploratory) and position % 5 == 0
        if use_exploration:
            candidates.append(
                RankedCandidate(exploratory[exploration_index], "exploration")
            )
            exploration_index += 1
        else:
            candidates.append(RankedCandidate(ordinary[ordinary_index], "exploitation"))
            ordinary_index += 1
    return RankingSelection(
        RESEARCH_RANKING_VERSION,
        seed,
        limit,
        tuple(candidates),
        excluded,
        limit // 5,
        len(exploratory),
    )
