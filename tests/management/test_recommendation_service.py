import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from huginn.management.application.read_models.recommendation_company import (
    RecommendationCompany,
)
from huginn.management.application.read_models.recommendation_profile import (
    RecommendationProfile,
)
from huginn.management.application.services.recommendations import RecommendationService
from huginn.management.domain.errors.errors import NotFoundError, ValidationDomainError
from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)
from huginn.matchmaking.domain.value_objects.ranking_observation import (
    RankingObservation,
)

NOW = datetime(2026, 10, 28, tzinfo=UTC)


class Work:
    committed = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        pass

    def commit(self):
        self.committed = True


class Store:
    def __init__(self):
        self.owner = uuid4()
        self.strategy = uuid4()
        self.saved = {}
        self.reviews = []
        self.icp = {
            "industries": [],
            "company_sizes": [],
            "geographies": [],
            "exclusions": [],
        }
        obs = RankingObservation(
            uuid4(),
            "Our onboarding software serves customers.",
            NOW - timedelta(days=1),
            NOW,
            "hn",
            "https://example.test",
        )
        self.company = RecommendationCompany(
            uuid4(), "Real source company", "example.test", None, None, None, (obs,)
        )

    def profile(self, user, strategy):
        if user != self.owner or strategy != self.strategy:
            return None
        return RecommendationProfile(
            self.strategy,
            json.dumps(
                {
                    "offering": {
                        "name": "Onboarding consulting",
                        "description": "Improve onboarding",
                    },
                    "icp": self.icp,
                }
            ),
            "Onboarding consulting. Improve onboarding",
        )

    def candidates(self, *args, **kwargs):
        return () if kwargs.get("offset", 0) else (self.company,)

    def active_strategy_ids(self, user):
        return (self.strategy,) if user == self.owner else ()

    def save_batch(self, user, batch, strategy, created, snapshot):
        self.saved[(user, batch)] = snapshot

    def get_batch(self, user, batch):
        return self.saved.get((user, batch))

    def latest_batch(self, user, strategy):
        return next(iter(self.saved.values()), None) if user == self.owner else None

    def append_feedback(self, user, batch, id, recommendation, created, payload):
        self.reviews.append((user, batch, payload))

    def feedback(self, user, batch):
        return tuple(
            payload
            for owner, bid, payload in self.reviews
            if owner == user and bid == batch
        )


def service():
    store = Store()
    work = Work()
    return (
        RecommendationService(
            lambda: work, repository_factory=lambda _: store, clock=lambda: NOW
        ),
        store,
        work,
    )


def test_generate_reads_real_sources_ranks_and_saves_complete_snapshot():
    svc, store, work = service()
    batch = svc.generate(store.owner, store.strategy, 5)
    assert work.committed
    assert batch["algorithm_version"] == "research-ranking-v1"
    assert batch["items"][0]["confidence"] == "low"
    assert batch["items"][0]["company"]["country"] is None
    assert batch["items"][0]["score"] == 27
    assert (
        batch["items"][0]["evidence"][0]["quote"]
        in store.company.observations[0].description
    )
    saved = json.loads(next(iter(store.saved.values())))
    assert (
        saved["ranking"]["input_snapshot"]["assessments"][0]["observations"][0][
            "description"
        ]
        == store.company.observations[0].description
    )
    assert svc.get(store.owner, UUID(batch["id"])) == batch
    assert svc.latest(store.owner, store.strategy) == batch


def test_feedback_is_appended_against_owned_occurrence_and_history_is_preserved():
    svc, store, _ = service()
    batch = svc.generate(store.owner, store.strategy, 5)
    rec = batch["items"][0]["id"]
    first = svc.review(
        store.owner,
        UUID(batch["id"]),
        rec,
        RecommendationFeedback("useful", ("service_fit",), next_step="research"),
    )
    second = svc.review(
        store.owner,
        UUID(batch["id"]),
        rec,
        RecommendationFeedback(
            "not_useful",
            ("customer_not_buyer",),
            correction="This is their product, not their own need.",
            outcome="not_relevant",
        ),
    )
    assert first["id"] != second["id"]
    assert svc.feedback(store.owner, UUID(batch["id"])) == [first, second]
    for user, identifier in ((uuid4(), rec), (store.owner, "missing")):
        with pytest.raises(NotFoundError):
            svc.review(
                user, UUID(batch["id"]), identifier, RecommendationFeedback("unsure")
            )
    assert len(store.reviews) == 2


def test_unknown_preferences_survive_but_explicit_company_exclusion_blocks():
    svc, store, _ = service()
    store.icp["exclusions"] = [
        {"kind": "company", "company_id": str(store.company.company_id)}
    ]
    assert svc.generate(store.owner, store.strategy, 5)["items"] == []
    with pytest.raises(NotFoundError):
        svc.generate(uuid4(), store.strategy, 5)
    with pytest.raises(ValidationDomainError):
        svc.generate(store.owner, store.strategy, 21)


def test_feedback_rejects_unknown_values_and_mutable_or_oversized_inputs():
    for kwargs in (
        {"usefulness": "bad"},
        {"usefulness": "useful", "reasons": ["service_fit"]},
        {"usefulness": "useful", "reasons": ("invented",)},
        {"usefulness": "useful", "correction": "x" * 2001},
    ):
        with pytest.raises(ValidationDomainError):
            RecommendationFeedback(**kwargs)


def test_sent_companies_are_removed_before_the_candidate_limit():
    svc, store, _ = service()
    previous = frozenset((store.company.company_id,))

    def candidates(terms, cutoff, as_of, limit, *, exclude_company_ids, offset=0):
        assert exclude_company_ids == previous
        return ()

    store.candidates = candidates
    assert (
        svc.generate(store.owner, store.strategy, 5, exclude_company_ids=previous)[
            "items"
        ]
        == []
    )


def test_icp_or_within_fields_and_across_fields_keeps_unknowns():
    svc, store, _ = service()
    store.icp.update(
        industries=[{"name": "Fintech"}, {"name": "Healthcare"}],
        company_sizes=[{"band": "11-50"}, {"band": "51-100"}],
        geographies=[
            {"kind": "country", "value": "UK"},
            {"kind": "country", "value": "Germany"},
        ],
    )
    store.company = replace(
        store.company,
        business_sector=("Healthcare",),
        country="DE",
        company_scale="51-100",
    )
    assert len(svc.generate(store.owner, store.strategy)["items"]) == 1
    for changed in (
        {"country": "US"},
        {"company_scale": "101-1000"},
        {"business_sector": ("Retail",)},
    ):
        original = store.company
        store.company = replace(original, **changed)
        assert svc.generate(store.owner, store.strategy)["items"] == []
        store.company = original
    store.company = replace(store.company, company_scale=None)
    item = svc.generate(store.owner, store.strategy)["items"][0]
    assert item["icp_fit"] == {
        "industry": "match",
        "size": "unknown",
        "country": "match",
    }
    assert "size" in " ".join(item["unknowns"]).lower()


def test_eligibility_is_applied_before_the_200_candidate_cap():
    svc, store, _ = service()
    store.icp["geographies"] = [{"kind": "country", "value": "UK"}]
    rejected = tuple(
        replace(store.company, company_id=uuid4(), country="US") for _ in range(200)
    )
    accepted = replace(store.company, country="UK")
    offsets = []

    def candidates(*args, offset=0, **kwargs):
        offsets.append(offset)
        return rejected if offset == 0 else (accepted,)

    store.candidates = candidates
    assert len(svc.generate(store.owner, store.strategy)["items"]) == 1
    assert offsets == [0, 200]


def test_weekly_selection_combines_strategies_deduplicates_and_saves_seven():
    svc, store, _ = service()
    first, second = store.strategy, uuid4()
    original_profile = store.profile
    store.active_strategy_ids = lambda user: (first, second)
    store.profile = lambda user, strategy: replace(
        original_profile(user, first), strategy_id=strategy
    )
    companies = tuple(replace(store.company, company_id=uuid4()) for _ in range(9))
    store.candidates = lambda *args, **kwargs: (
        () if kwargs.get("offset", 0) else companies
    )
    batch = svc.generate_weekly(store.owner)
    assert batch["kind"] == "weekly"
    assert batch["strategy_id"] == batch["items"][0]["strategies"][0]["id"]
    assert len(batch["items"]) == 7
    assert len({item["company"]["id"] for item in batch["items"]}) == 7
    assert all(
        {entry["id"] for entry in item["strategies"]} == {str(first), str(second)}
        for item in batch["items"]
    )
    assert len(store.saved) == 1
    saved = svc.get(store.owner, UUID(batch["id"]))
    svc.generate(store.owner, first)
    assert svc.get(store.owner, UUID(batch["id"])) == saved
