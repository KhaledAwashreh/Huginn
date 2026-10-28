from dataclasses import replace
from uuid import UUID

import pytest

from huginn.matchmaking.domain.policies.research_scoring import score_assessment
from huginn.matchmaking.domain.policies.research_selection import (
    select_research_candidates,
)
from huginn.matchmaking.domain.value_objects.ranking_restriction import (
    RankingRestriction,
)
from tests.matchmaking.domain.policies.test_research_scoring import AS_OF, assessment


def scores(count=12):
    return tuple(
        score_assessment(
            assessment(
                company_id=UUID(int=100 + i),
                assessment_id=UUID(int=200 + i),
                service_fit="direct" if i < 8 else "plausible",
                service_basis="observed" if i < 8 else "inferred",
            ),
            AS_OF,
        )
        for i in range(count)
    )


def test_small_batch_uses_relevance_order_without_exploration():
    result = select_research_candidates(tuple(reversed(scores())), 3, "seed")
    assert result is not None, "Selection must produce a reproducible ranked batch"
    assert [r.score.assessment.company_id for r in result.candidates] == [
        UUID(int=i) for i in (100, 101, 102)
    ]
    assert result.actual_exploration_slots == 0
    assert all(r.selection_type == "exploitation" for r in result.candidates)


def test_one_in_five_is_a_deterministic_uncertain_tail_candidate_with_actual_score():
    original = scores()
    result = select_research_candidates(original, 5, "seed")
    assert result is not None
    assert len(result.candidates) == 5
    assert result.requested_exploration_slots == result.actual_exploration_slots == 1
    assert result.candidates[4].selection_type == "exploration"
    assert result.candidates[4].score.assessment.company_id in {
        UUID(int=i) for i in (108, 109, 110, 111)
    }
    assert result.candidates[4].score in original
    assert select_research_candidates(tuple(reversed(original)), 5, "seed") == result


def test_two_exploratory_slots_are_interleaved_in_a_ten_candidate_batch():
    result = select_research_candidates(scores(), 10, "seed")
    assert result is not None
    assert result.actual_exploration_slots == 2
    assert [
        i
        for i, r in enumerate(result.candidates, 1)
        if r.selection_type == "exploration"
    ] == [5, 10]
    assert len({r.score.assessment.company_id for r in result.candidates}) == 10


def test_no_plausible_uncertain_tail_falls_back_to_regular_score_order():
    values = scores(8)
    result = select_research_candidates(values, 5, "seed")
    assert result is not None
    assert result.actual_exploration_slots == 0
    assert [r.score for r in result.candidates] == list(values[:5])


def test_a_short_pool_never_inflates_exploration_above_twenty_percent():
    result = select_research_candidates(scores(3), 10, "seed")
    assert result is not None
    assert len(result.candidates) == 3
    assert result.actual_exploration_slots == 0


def test_company_duplicates_choose_best_eligible_assessment_without_mixing_features():
    best = scores(1)[0]
    weaker = score_assessment(
        replace(best.assessment, assessment_id=UUID(int=999), service_fit="adjacent"),
        AS_OF,
    )
    result = select_research_candidates((weaker, best), 5, "seed")
    assert result is not None
    assert len(result.candidates) == 1
    assert result.candidates[0].score == best


def test_excluded_hypothesis_does_not_block_a_different_eligible_company_hypothesis():
    values = scores(2)
    denied = replace(values[0].assessment, assessment_id=UUID(int=999))
    restriction = RankingRestriction(
        "proposed_engagement",
        "conflict",
        True,
        "Source-backed scope conflict",
        denied.evidence[0],
    )
    blocked = score_assessment(replace(denied, restrictions=(restriction,)), AS_OF)
    result = select_research_candidates((blocked,) + values, 5, "seed")
    assert result is not None
    assert len(result.candidates) == 2
    assert result.excluded_company_ids == ()
    only_blocked = select_research_candidates((blocked, values[1]), 5, "seed")
    assert only_blocked is not None
    assert only_blocked.excluded_company_ids == (denied.company_id,)


def test_invalid_limits_seed_duplicate_assessment_and_mixed_asof_rejected():
    values = scores()
    for limit in (True, 0, -1, 101, 1.5):
        with pytest.raises(ValueError):
            select_research_candidates(values, limit, "seed")
    with pytest.raises(ValueError):
        select_research_candidates(values, 5, " ")
    with pytest.raises(ValueError):
        select_research_candidates(values + values[:1], 5, "seed")
    with pytest.raises(ValueError):
        select_research_candidates(
            (values[0], replace(values[1], as_of=AS_OF.replace(day=24))), 5, "seed"
        )


def test_empty_input_is_a_valid_empty_result_with_no_invented_slots():
    result = select_research_candidates((), 5, "seed")
    assert result is not None
    assert result.candidates == ()
    assert result.actual_exploration_slots == 0
