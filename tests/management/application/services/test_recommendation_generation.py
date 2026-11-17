import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from uuid import uuid4

import pytest

from huginn.management.application.errors.errors import RateLimitError
from huginn.management.application.read_models.generated_recommendation_reference import (
    GeneratedRecommendationReference,
)
from huginn.management.application.read_models.recommendation_company import (
    RecommendationCompany,
)
from huginn.management.application.read_models.recommendation_profile import (
    RecommendationProfile,
)
from huginn.management.application.requests.generate_recommendations_request import (
    GenerateRecommendationsRequest,
)
from huginn.management.application.services.recommendation_generation import (
    RecommendationGenerationService,
)
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.common import Principal
from huginn.matchmaking.domain.value_objects.business_company_state import (
    BusinessCompanyState,
)
from huginn.matchmaking.domain.value_objects.ranking_observation import (
    RankingObservation,
)


def test_on_demand_request_defaults_to_ten_and_has_no_business_or_actor_input():
    request = GenerateRecommendationsRequest(strategy_id=uuid4())
    assert request.limit == 10
    assert not hasattr(request, "business_id")
    assert not hasattr(request, "owner_user_id")


@pytest.mark.parametrize("limit", (0, 21, True, 1.5))
def test_on_demand_request_rejects_limits_outside_one_through_twenty(limit):
    with pytest.raises(ValidationDomainError):
        GenerateRecommendationsRequest(strategy_id=uuid4(), limit=limit)


NOW = datetime(2026, 11, 14, 12, tzinfo=UTC)


class _Work:
    def __init__(self, owner, business):
        self.connection = object()
        self.businesses = SimpleNamespace(
            get_by_owner_user_id=lambda user: business if user == owner else None,
            get_by_id=lambda identifier: (
                business if identifier == business.id else None
            ),
        )
        self.commands = SimpleNamespace(record=self._record)
        self.offer_cycles = SimpleNamespace(list_expired_preparing=lambda *args: ())
        self.receipts = []
        self.committed = False
        self.locked_pairs = []

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def _record(self, receipt):
        self.receipts.append(receipt)
        return receipt

    def commit(self):
        self.committed = True

    def lock_business_company(self, business_id, company_id):
        self.locked_pairs.append((business_id, company_id))


class _CleanupWork:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    offer_cycles = SimpleNamespace(list_expired_preparing=lambda *args: ())

    def lock_business_company(self, *args):
        pass


class _Source:
    def __init__(self, owner, strategy, run_times=()):
        self.owner = owner
        self.strategy = strategy
        self.run_times = run_times
        self.locked = False
        self.configuration_events = []
        self.profile_reads = 0
        self.profile_value = RecommendationProfile(
            strategy,
            json.dumps(
                {
                    "strategy": {"id": str(strategy), "name": "Strategy"},
                    "offering": {
                        "id": str(uuid4()),
                        "name": "Onboarding services",
                        "description": "Customer onboarding consulting",
                    },
                    "icp": {
                        "id": str(uuid4()),
                        "industries": [],
                        "company_sizes": [],
                        "geographies": [],
                        "exclusions": [],
                    },
                    "professional_profile": None,
                }
            ),
            "Onboarding services customer onboarding consulting",
        )

    def lock_configuration(self, business_id):
        self.configuration_events.append("configuration")

    def lock_successful_run_window(self, business_id):
        self.configuration_events.append("quota")
        self.locked = True

    def successful_on_demand_runs_since(self, business_id, since):
        assert self.locked
        return self.run_times

    def profile(self, owner_user_id, strategy_id):
        self.profile_reads += 1
        if owner_user_id == self.owner and strategy_id == self.strategy:
            return self.profile_value
        return None

    def active_profiles(self, owner_user_id):
        self.configuration_events.append("profiles")
        value = self.profile(owner_user_id, self.strategy)
        return () if value is None else (value,)

    def candidates(self, *args, **kwargs):
        return ()

    def company_states(self, business_id, company_ids, as_of):
        assert company_ids == ()
        return ()


def _generation_service(run_times=()):
    owner, strategy, business_id = uuid4(), uuid4(), uuid4()
    business = SimpleNamespace(id=business_id, owner_user_id=owner)
    work = _Work(owner, business)
    source = _Source(owner, strategy, run_times)
    service = RecommendationGenerationService(
        lambda: work,
        source_factory=lambda connection: source,
        clock=lambda: NOW,
    )
    return service, work, source, Principal(uuid4(), owner), strategy, business_id


def test_successful_empty_run_is_receipted_and_counts_as_on_demand_success():
    service, work, source, principal, strategy, business_id = _generation_service()
    response = service.execute(principal, GenerateRecommendationsRequest(strategy))
    assert response.business_id == business_id
    assert response.references == ()
    assert source.locked
    assert work.committed
    receipt = work.receipts[0]
    assert receipt.scope == "recommendation_generation:on_demand"
    assert receipt.resource_kind == "recommendation_generation_run"
    assert receipt.resource_version == 1
    assert receipt.result_snapshot.to_json_object()["references"] == []


def test_rate_limited_run_does_not_read_profile_or_record_success():
    full_window = tuple(NOW - timedelta(minutes=14) for _ in range(6))
    service, work, source, principal, strategy, _ = _generation_service(full_window)
    with pytest.raises(RateLimitError) as error:
        service.execute(principal, GenerateRecommendationsRequest(strategy))
    assert error.value.retry_after_seconds == 60
    assert source.locked
    assert source.profile_reads == 0
    assert work.receipts == []
    assert not work.committed


def test_weekly_run_uses_business_owner_without_on_demand_quota_lock():
    service, work, source, _, _, business_id = _generation_service()
    response = service.execute_weekly(business_id)
    assert response.business_id == business_id
    assert source.profile_reads == 1
    assert not source.locked
    assert work.receipts[0].scope == "recommendation_generation:weekly"
    assert work.committed


def test_suppressed_candidates_do_not_consume_the_two_hundred_eligible_cap():
    now = datetime(2026, 11, 14, tzinfo=UTC)
    business_id = uuid4()
    candidates = tuple(
        RecommendationCompany(
            uuid4(),
            f"Company {index}",
            f"company-{index}.example.test",
            None,
            None,
            None,
            (
                RankingObservation(
                    uuid4(),
                    "Career coaching services",
                    now - timedelta(days=1),
                    now,
                    "hn",
                    "https://source.example/item",
                ),
            ),
        )
        for index in range(201)
    )
    suppressed = {company.company_id for company in candidates[:200]}

    class Source:
        def candidates(self, terms, cutoff, as_of, limit, *, offset=0, **kwargs):
            assert limit == 200
            return candidates[offset : offset + limit]

        def company_states(self, requested_business_id, company_ids, as_of):
            assert requested_business_id == business_id
            return tuple(
                BusinessCompanyState(
                    cooldown_until=now + timedelta(days=1)
                    if company_id in suppressed
                    else None
                )
                for company_id in company_ids
            )

    service = object.__new__(RecommendationGenerationService)
    service._uow_factory = _CleanupWork
    service._clock = lambda: now
    companies, _, assessments = service._assess_candidates(
        Source(),
        business_id,
        RecommendationProfile(uuid4(), "{}", "career coaching"),
        {},
        ("coaching",),
        ("coaching",),
        {},
        now,
    )

    assert tuple(companies) == (candidates[-1].company_id,)
    assert len(assessments) == 1
    assert assessments[0].company_id == candidates[-1].company_id


def test_suppressed_company_is_gated_before_fit_or_topic_reassessment(monkeypatch):
    from huginn.management.application.services import recommendation_generation

    company = RecommendationCompany(
        uuid4(),
        "Suppressed company",
        "suppressed.example.test",
        None,
        None,
        None,
        (
            RankingObservation(
                uuid4(),
                "Career coaching services",
                NOW - timedelta(days=1),
                NOW,
                "hn",
                "https://source.example/item",
            ),
        ),
    )
    calls = []

    class Source:
        def candidates(self, *args, **kwargs):
            return (company,)

        def company_states(self, business_id, company_ids, as_of):
            calls.append(("state", company_ids))
            return (BusinessCompanyState(rejected=True),)

    def should_not_assess(*args, **kwargs):
        calls.append(("assessment", None))
        raise AssertionError("suppressed company was reassessed")

    monkeypatch.setattr(
        recommendation_generation, "assess_company_fit", should_not_assess
    )
    monkeypatch.setattr(
        recommendation_generation, "assess_topic_overlap", should_not_assess
    )
    service = object.__new__(RecommendationGenerationService)
    service._uow_factory = _CleanupWork
    service._clock = lambda: NOW
    companies, _, assessments = service._assess_candidates(
        Source(),
        uuid4(),
        RecommendationProfile(uuid4(), "{}", "career coaching"),
        {},
        ("coaching",),
        ("coaching",),
        {},
        NOW,
    )

    assert calls == [("state", (company.company_id,))]
    assert companies == {}
    assert assessments == []


def test_pair_recheck_uses_post_lock_time_and_revalidates_source_before_writes():
    business_id, company_id, strategy_id = uuid4(), uuid4(), uuid4()
    company = RecommendationCompany(
        company_id,
        "Company",
        "company.example.test",
        None,
        None,
        None,
        (
            RankingObservation(
                uuid4(),
                "Career coaching services",
                NOW - timedelta(days=1),
                NOW,
                "hn",
                "https://source.example/item",
            ),
        ),
    )
    observed = {}

    class Source:
        def candidate_is_current(self, candidate, cutoff, as_of):
            observed["candidate"] = (candidate, cutoff, as_of)
            return True

        def company_states(self, requested_business_id, company_ids, as_of):
            observed["eligibility_time"] = as_of
            if as_of > NOW:
                return (BusinessCompanyState(rejected=True),)
            return (BusinessCompanyState(),)

    class Work:
        def lock_business_company(self, *args):
            raise AssertionError("caller must acquire ordered pair locks first")

    service = object.__new__(RecommendationGenerationService)
    result = service._persist_revision(
        Work(),
        Source(),
        business_id,
        company_id,
        (strategy_id,),
        [
            (
                RecommendationProfile(strategy_id, "{}", "service"),
                {},
                company,
                None,
                {},
                "seed",
            )
        ],
        NOW,
        NOW + timedelta(seconds=2),
        None,
    )

    assert result is None
    assert observed["candidate"][2] == NOW + timedelta(seconds=2)
    assert observed["eligibility_time"] == NOW + timedelta(seconds=2)


def test_selected_company_locks_are_ordered_and_final_recheck_uses_new_clock(
    monkeypatch,
):
    service, work, source, principal, strategy, _ = _generation_service()
    company_ids = (uuid4(), uuid4())
    companies = tuple(
        RecommendationCompany(
            company_id,
            f"Company {index}",
            f"company-{index}.example.test",
            None,
            None,
            None,
            (
                RankingObservation(
                    uuid4(),
                    "Onboarding services help customer onboarding",
                    NOW - timedelta(days=1),
                    NOW,
                    "hn",
                    f"https://source.example/{index}",
                ),
            ),
        )
        for index, company_id in enumerate(company_ids)
    )

    class Source:
        candidate_times = []
        state_times = []

        def lock_successful_run_window(self, business_id):
            pass

        def successful_on_demand_runs_since(self, business_id, since):
            return ()

        def profile(self, owner_user_id, strategy_id):
            return source.profile_value

        def candidates(self, terms, cutoff, as_of, limit, **kwargs):
            self.candidate_times.append(as_of)
            return companies

        def company_states(self, business_id, requested_ids, as_of):
            self.state_times.append(as_of)
            return tuple(BusinessCompanyState() for _ in requested_ids)

        def candidate_is_current(self, company, cutoff, as_of):
            self.state_times.append(as_of)
            return True

    source_query = Source()
    times = iter(
        (
            NOW,
            NOW,
            NOW,
            NOW + timedelta(seconds=3),
            NOW + timedelta(seconds=3),
            NOW + timedelta(seconds=3),
            NOW + timedelta(seconds=3),
        )
    )
    service._clock = lambda: next(times)
    service._source_factory = lambda connection: source_query
    monkeypatch.setattr(
        RecommendationGenerationService,
        "_persist_revision",
        lambda self, *args, **kwargs: GeneratedRecommendationReference(
            uuid4(), uuid4(), 1
        ),
    )

    response = service.execute(
        principal, GenerateRecommendationsRequest(strategy, limit=2)
    )

    assert len(response.references) == 2
    assert tuple(company_id for _, company_id in work.locked_pairs) == tuple(
        sorted(company_ids, key=str)
    )
    assert source_query.candidate_times == [NOW]
    assert all(
        value == NOW + timedelta(seconds=3) for value in source_query.state_times[2:]
    )


@pytest.mark.parametrize("weekly", [False, True])
@pytest.mark.parametrize("count", [0, 2])
def test_simple_mode_requires_exactly_one_active_profile(weekly, count, monkeypatch):
    service, work, source, principal, strategy, business_id = _generation_service()
    service._simple_discovery_enabled = True
    monkeypatch.setattr(
        source, "active_profiles", lambda owner: (source.profile_value,) * count
    )
    with pytest.raises(ValidationDomainError, match="exactly one"):
        if weekly:
            service.execute_weekly(business_id)
        else:
            service.execute(principal, GenerateRecommendationsRequest(strategy))
    assert not work.committed
    assert work.receipts == []


@pytest.mark.parametrize("weekly", [False, True])
def test_simple_mode_generates_from_single_active_profile(weekly):
    service, work, source, principal, strategy, business_id = _generation_service()
    service._simple_discovery_enabled = True
    result = (
        service.execute_weekly(business_id)
        if weekly
        else service.execute(principal, GenerateRecommendationsRequest(strategy))
    )
    assert result.business_id == business_id
    assert work.committed
    assert source.configuration_events == (
        ["configuration", "profiles"]
        if weekly
        else ["configuration", "quota", "profiles"]
    )


def test_simple_mode_rejects_strategy_outside_single_active_profile():
    service, work, source, principal, strategy, business_id = _generation_service()
    service._simple_discovery_enabled = True
    with pytest.raises(ValidationDomainError, match="setup changed"):
        service.execute(principal, GenerateRecommendationsRequest(uuid4()))
    assert work.receipts == []


@pytest.mark.parametrize("weekly", [False, True])
def test_full_mode_keeps_multiple_active_profiles(weekly, monkeypatch):
    service, work, source, principal, strategy, business_id = _generation_service()
    monkeypatch.setattr(
        source,
        "active_profiles",
        lambda owner: (source.profile_value, source.profile_value),
    )
    result = (
        service.execute_weekly(business_id)
        if weekly
        else service.execute(principal, GenerateRecommendationsRequest(strategy))
    )
    assert result.business_id == business_id
    assert work.committed
