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
    ):
        self.reads = 0
        self.commits = 0
        self.inserts = []
        self.windows = []
        self.failure = failure
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

    def insert(self, user, company):
        self.inserts.append(company)
        return None

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
    uow = Uow(
        (strategy(user), strategy(user)), tuple(CompanyCandidate(id) for id in ids)
    )
    response = MatchmakingService(lambda: uow, Clock(), lambda delay: None).execute(
        MatchmakingRequest(user, NOW)
    )
    assert (
        response.unique_candidates_count == response.existing_matches_skipped_count == 2
    )
    assert response.strategies_evaluated == 2
    assert uow.reads == 1 and uow.inserts == ids and uow.commits == 1


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
    first = Uow(
        (strategy(user),), (CompanyCandidate(uuid4()),), RetryableTransactionError()
    )
    second = Uow((strategy(user),), ())
    attempts = iter((first, second))
    delays = []
    clock = Clock()
    response = MatchmakingService(lambda: next(attempts), clock, delays.append).execute(
        MatchmakingRequest(user, NOW)
    )
    assert (
        response.unique_candidates_count == 0 and delays == [0.05] and clock.calls == 1
    )
    assert first.windows == second.windows


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
            else (CompanyCandidate(company),)
        )

    uow.candidates.find_candidates = candidates
    response = MatchmakingService(lambda: uow, Clock()).execute(
        MatchmakingRequest(user, NOW)
    )
    assert response.unique_candidates_count == 1 and uow.inserts == [company]


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
