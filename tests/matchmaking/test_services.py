from datetime import UTC, datetime
from types import SimpleNamespace
from uuid import uuid4

import pytest

from huginn.matchmaking.application.errors.execution import (
    CommitOutcomeUnknownExecutionError,
    InputValidationError,
)
from huginn.matchmaking.application.read_models.company_candidate import (
    CompanyCandidate,
)
from huginn.matchmaking.application.read_models.strategy_configuration import (
    StrategyConfiguration,
)
from huginn.matchmaking.application.read_models.user_availability import (
    UserAvailability,
)
from huginn.matchmaking.application.requests.batch_matchmaking_request import (
    BatchMatchmakingRequest,
)
from huginn.matchmaking.application.requests.matchmaking_request import (
    MatchmakingRequest,
)
from huginn.matchmaking.application.services.batch_matchmaking_service import (
    MatchmakingBatchService,
)
from huginn.matchmaking.application.services.matchmaking_service import (
    MatchmakingService,
)
from huginn.matchmaking.domain.entities.match import Match, MatchStatus
from huginn.matchmaking.persistence.errors.database import (
    CommitOutcomeUnknownError,
    RetryableTransactionError,
)

NOW = datetime(2026, 10, 1, tzinfo=UTC)


class Clock:
    calls = 0

    def now(self):
        self.calls += 1
        return NOW


class Uow:
    def __init__(
        self,
        strategies=(),
        candidates=(),
        failure=None,
        availability=UserAvailability.ACTIVE,
        insert_result=None,
    ):
        self.reads = 0
        self.commits = 0
        self.inserts = []
        self.insert_calls = []
        self.windows = []
        self.failure = failure
        self.insert_result = insert_result
        self.configuration = SimpleNamespace(
            user_availability=lambda user: availability,
            list_active_strategies=lambda user: strategies,
        )
        self.candidates = SimpleNamespace(find_candidates=self.find)
        self.matches = SimpleNamespace(insert_if_absent=self.insert)
        self.rows = candidates

    def find(self, criteria, window):
        self.reads += 1
        self.windows.append(window)
        return self.rows

    def insert(self, user, company, *, observation_ids, window):
        self.inserts.append(company)
        self.insert_calls.append((user, company, observation_ids, window))
        return self.insert_result

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def commit(self):
        self.commits += 1
        if self.failure:
            raise self.failure

    def rollback(self):
        pass


def strategy(user, *, industries=({"name": "Software"},)):
    return StrategyConfiguration(
        uuid4(),
        user,
        "Strategy",
        uuid4(),
        uuid4(),
        industries,
        ({"band": "11-100"},),
        ({"kind": "country", "value": "US"},),
        (),
    )


def test_union_memoization_counts_existing_and_commits():
    user = uuid4()
    ids = sorted((uuid4(), uuid4()))
    proof = (uuid4(),)
    uow = Uow(
        (strategy(user), strategy(user)),
        tuple(CompanyCandidate(id, proof) for id in ids),
    )
    as_of = datetime(2026, 10, 2, tzinfo=UTC)
    response = MatchmakingService(lambda: uow, Clock(), lambda delay: None).execute(
        MatchmakingRequest(user, NOW, as_of)
    )
    assert (
        response.unique_candidates_count == response.existing_matches_skipped_count == 2
    )
    assert response.strategies_evaluated == 2
    assert uow.reads == 1 and uow.inserts == ids and uow.commits == 1
    assert [call[2] for call in uow.insert_calls] == [proof, proof]
    assert all(call[3] == uow.windows[0] for call in uow.insert_calls)
    assert all(call[3].as_of == as_of for call in uow.insert_calls)


def test_incomplete_and_disabled_do_not_query_candidates():
    user = uuid4()
    uow = Uow((strategy(user, industries=()),))
    response = MatchmakingService(lambda: uow, Clock(), lambda delay: None).execute(
        MatchmakingRequest(user, NOW)
    )
    assert response.strategies_skipped == 1 and uow.reads == 0
    disabled = Uow(availability=UserAvailability.DISABLED)
    response = MatchmakingService(
        lambda: disabled, Clock(), lambda delay: None
    ).execute(MatchmakingRequest(user, NOW))
    assert response.status == "disabled_user" and disabled.commits == 0


def test_retry_discards_attempt_and_keeps_window():
    user = uuid4()
    first_proof = (uuid4(),)
    first = Uow(
        (strategy(user),),
        (CompanyCandidate(uuid4(), first_proof),),
        RetryableTransactionError(),
    )
    retry_company = uuid4()
    retry_proof = (uuid4(),)
    second = Uow((strategy(user),), (CompanyCandidate(retry_company, retry_proof),))
    attempts = iter((first, second))
    delays = []
    clock = Clock()
    response = MatchmakingService(lambda: next(attempts), clock, delays.append).execute(
        MatchmakingRequest(user, NOW)
    )
    assert (
        response.unique_candidates_count == 1 and delays == [0.05] and clock.calls == 1
    )
    assert first.windows == second.windows
    assert first.insert_calls[0][2] == first_proof
    assert second.insert_calls[0][2] == retry_proof
    assert second.insert_calls == [
        (user, retry_company, retry_proof, second.windows[0])
    ]


def test_commit_uncertainty_never_retries():
    user = uuid4()
    uow = Uow(failure=CommitOutcomeUnknownError())
    calls = []
    with pytest.raises(CommitOutcomeUnknownExecutionError):
        MatchmakingService(lambda: uow, Clock(), calls.append).execute(
            MatchmakingRequest(user, NOW)
        )
    assert not calls


def test_invalid_and_empty_batch_open_no_database():
    def forbidden():
        raise AssertionError("database accessed")

    service = MatchmakingService(forbidden, Clock(), lambda delay: None)
    with pytest.raises(InputValidationError):
        service.execute(MatchmakingRequest("bad", NOW))
    response = MatchmakingBatchService(service, Clock(), forbidden).execute(
        BatchMatchmakingRequest((), NOW)
    )
    assert response.responses == response.failures == ()


def test_retry_exhaustion_has_three_fresh_attempts():
    from huginn.matchmaking.application.errors.execution import (
        RetriesExhaustedExecutionError,
    )

    attempts = []
    delays = []

    def factory():
        uow = Uow(failure=RetryableTransactionError())
        attempts.append(uow)
        return uow

    with pytest.raises(RetriesExhaustedExecutionError):
        MatchmakingService(factory, Clock(), delays.append).execute(
            MatchmakingRequest(uuid4(), NOW)
        )
    assert len(attempts) == 3 and delays == [0.05, 0.10]


def test_programming_error_propagates():
    class Broken(Uow):
        def commit(self):
            raise AttributeError("bug")

    with pytest.raises(AttributeError):
        MatchmakingService(Broken, Clock()).execute(MatchmakingRequest(uuid4(), NOW))


def test_batch_order_dedup_partial_failure_and_fixed_time():
    from huginn.matchmaking.application.errors.execution import (
        DatabaseFailureExecutionError,
    )
    from huginn.matchmaking.application.responses.matchmaking_response import (
        MatchmakingResponse,
        MatchmakingStatus,
    )

    ids = sorted((uuid4(), uuid4(), uuid4()))
    calls = []
    clock = Clock()

    class Service:
        def execute(self, request):
            calls.append(request)
            if request.user_id == ids[1]:
                raise DatabaseFailureExecutionError("secret")
            return MatchmakingResponse(
                request.user_id,
                MatchmakingStatus.SUCCEEDED,
                request.cutoff,
                request.as_of,
                0,
                0,
                0,
                (),
                0,
                (),
            )

    batch = MatchmakingBatchService(Service(), clock).execute(
        BatchMatchmakingRequest(tuple(reversed(ids)) + (ids[0],), NOW)
    )
    assert [r.user_id for r in batch.responses] == [ids[0], ids[2]]
    assert [r.user_id for r in batch.failures] == [ids[1]]
    assert (
        [r.user_id for r in calls] == ids
        and all(r.as_of == NOW for r in calls)
        and clock.calls == 1
    )


def test_readiness_failure_maps_all_requested_users_after_validation():
    from huginn.matchmaking.persistence.errors.database import DatabaseUnavailableError

    def readiness():
        raise DatabaseUnavailableError("secret")

    ids = sorted((uuid4(), uuid4()))
    batch = MatchmakingBatchService(None, Clock(), readiness)
    with pytest.raises(InputValidationError):
        batch.execute(BatchMatchmakingRequest(("bad",), NOW))
    response = batch.execute(BatchMatchmakingRequest(tuple(reversed(ids)), NOW))
    assert [r.user_id for r in response.failures] == ids and response.responses == ()
    assert all(r.reason == "database_unavailable" for r in response.failures)


def test_exclusion_scope_can_qualify_through_another_strategy():
    from dataclasses import replace

    user = uuid4()
    company = uuid4()
    blocked = replace(
        strategy(user), exclusions=({"kind": "company", "company_id": str(company)},)
    )
    allowed = strategy(user)
    uow = Uow((blocked, allowed))

    def candidates(criteria, window):
        return (
            ()
            if company in criteria.excluded_company_ids
            else (CompanyCandidate(company, (uuid4(),)),)
        )

    uow.candidates.find_candidates = candidates
    response = MatchmakingService(lambda: uow, Clock()).execute(
        MatchmakingRequest(user, NOW)
    )
    assert response.unique_candidates_count == 1 and uow.inserts == [company]


def test_distinct_criteria_union_deduplicates_and_sorts_company_evidence():
    from dataclasses import replace

    user = uuid4()
    company = uuid4()
    other_company = uuid4()
    proof_a, proof_b, proof_c = sorted(uuid4() for _ in range(3))
    first = strategy(user)
    second = replace(first, strategy_id=uuid4(), industries=({"name": "Finance"},))
    uow = Uow((first, second))
    candidate_calls = []

    def candidates(criteria, window):
        candidate_calls.append((criteria, window))
        if criteria.industries[0] == "Software":
            return (
                CompanyCandidate(company, (proof_b, proof_a)),
                CompanyCandidate(other_company, (proof_c,)),
            )
        return (CompanyCandidate(company, (proof_a, proof_c)),)

    uow.candidates.find_candidates = candidates
    as_of = datetime(2026, 10, 4, tzinfo=UTC)
    response = MatchmakingService(lambda: uow, Clock()).execute(
        MatchmakingRequest(user, NOW, as_of)
    )

    assert len(candidate_calls) == 2
    assert uow.inserts == sorted((company, other_company))
    calls = {call[1]: call for call in uow.insert_calls}
    assert calls[company][2] == (proof_a, proof_b, proof_c)
    assert calls[other_company][2] == (proof_c,)
    assert all(
        call[3].cutoff == NOW and call[3].as_of == as_of for call in calls.values()
    )
    assert response.unique_candidates_count == 2


def test_created_match_receives_selected_evidence_and_original_window():
    user = uuid4()
    company = uuid4()
    observation_ids = tuple(sorted((uuid4(), uuid4())))
    created_match = Match(uuid4(), user, company, MatchStatus.NEW, None, NOW, NOW)
    uow = Uow(
        (strategy(user),),
        (CompanyCandidate(company, observation_ids),),
        insert_result=created_match,
    )
    as_of = datetime(2026, 10, 5, tzinfo=UTC)

    response = MatchmakingService(lambda: uow, Clock()).execute(
        MatchmakingRequest(user, NOW, as_of)
    )

    assert response.created_matches == (created_match,)
    assert uow.insert_calls == [(user, company, observation_ids, uow.windows[0])]
    assert uow.insert_calls[0][3].cutoff == NOW
    assert uow.insert_calls[0][3].as_of == as_of


def test_excluded_strategy_does_not_contribute_its_observations():
    from dataclasses import replace

    user = uuid4()
    company = uuid4()
    blocked = replace(
        strategy(user),
        geographies=({"kind": "region", "value": "Europe"},),
    )
    allowed = strategy(user)
    allowed_proof = uuid4()
    uow = Uow((blocked, allowed))
    candidate_calls = []

    def candidates(criteria, window):
        candidate_calls.append(criteria)
        return (CompanyCandidate(company, (allowed_proof,)),)

    uow.candidates.find_candidates = candidates
    MatchmakingService(lambda: uow, Clock()).execute(MatchmakingRequest(user, NOW))

    assert len(candidate_calls) == 1
    assert uow.insert_calls[0][2] == (allowed_proof,)


def test_region_exclusion_skips_without_candidate_query():
    from dataclasses import replace

    user = uuid4()
    region = replace(
        strategy(user),
        exclusions=(
            {"kind": "geography", "geography": {"kind": "region", "value": "Europe"}},
        ),
    )
    uow = Uow((region,))
    response = MatchmakingService(lambda: uow, Clock()).execute(
        MatchmakingRequest(user, NOW)
    )
    assert (
        response.skipped_strategies[0].reason == "unsupported_region" and uow.reads == 0
    )
