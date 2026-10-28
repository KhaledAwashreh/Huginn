"""Connect owned strategy/source snapshots, ranking and feedback; research-ranking.md."""

import json
import logging
from collections.abc import Callable
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from huginn.management.application.policies.recommendation_preferences import (
    country_preference,
    excluded_from_research,
    preference_status,
    validate_exclusions,
)
from huginn.management.application.protocols.recommendations import (
    RecommendationRepository,
)
from huginn.management.domain.errors.errors import NotFoundError, ValidationDomainError
from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol
from huginn.matchmaking.application.requests.research_ranking_request import (
    ResearchRankingRequest,
)
from huginn.matchmaking.application.serializers.research_ranking import (
    serialize_research_ranking,
)
from huginn.matchmaking.application.services.research_ranking_service import (
    ResearchRankingService,
)
from huginn.matchmaking.domain.policies.lexical_research import (
    assess_topic_overlap,
    offering_terms,
)

logger = logging.getLogger(__name__)


def _dump(value):
    return json.dumps(value, sort_keys=True, allow_nan=False)


class RecommendationService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        repository_factory: Callable[[UnitOfWorkProtocol], RecommendationRepository],
        clock: Callable[[], datetime] | None = None,
    ):
        self._uow = unit_of_work_factory
        self._repository = repository_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def generate(
        self,
        user_id: UUID,
        strategy_id: UUID,
        limit: int = 10,
        *,
        exclude_company_ids: frozenset[UUID] = frozenset(),
    ) -> dict:
        if type(limit) is not int or not 1 <= limit <= 20:
            raise ValidationDomainError(
                "Recommendation limit must be between one and twenty"
            )
        now = self._clock()
        logger.info("Recommendation batch generation started")
        with self._uow() as work:
            repository = self._repository(work)
            profile = repository.profile(user_id, strategy_id)
            if profile is None:
                raise NotFoundError("Active strategy not found")
            profile_data = json.loads(profile.snapshot_json)
            terms = offering_terms(profile.offering_text)
            if not terms:
                raise ValidationDomainError(
                    "Offering needs descriptive topics before generating recommendations"
                )
            companies = repository.candidates(
                terms,
                now - timedelta(days=365),
                now,
                200,
                exclude_company_ids=exclude_company_ids,
            )
            icp = profile_data.get("icp", {})
            validate_exclusions(icp.get("exclusions", []))
            assessments = []
            for company in companies:
                if company.company_id in exclude_company_ids:
                    continue
                if excluded_from_research(company, icp.get("exclusions", [])):
                    continue
                assessment = assess_topic_overlap(
                    company.company_id,
                    company.observations,
                    terms,
                    now,
                    industry_match=preference_status(
                        company.business_sector, icp.get("industries", []), "name"
                    ),
                    size_match=preference_status(
                        company.company_scale, icp.get("company_sizes", []), "band"
                    ),
                    country_match=country_preference(
                        company.country, icp.get("geographies", [])
                    ),
                )
                if assessment is not None:
                    assessments.append(assessment)
            profile_data["retrieval_terms"] = list(terms)
            if exclude_company_ids:
                profile_data["previously_sent_company_ids"] = sorted(
                    str(value) for value in exclude_company_ids
                )
            request = ResearchRankingRequest(
                str(strategy_id),
                _dump(profile_data),
                "topic-overlap-v1",
                now,
                limit,
                f"{strategy_id}/{now.date().isoformat()}",
                tuple(assessments),
            )
            result = ResearchRankingService().execute(request)
            snapshot = serialize_research_ranking(result)
            identities = {str(company.company_id): company for company in companies}
            items = []
            for item in snapshot["recommendations"]:
                company = identities[item["company_id"]]
                sources = {
                    str(source.observation_id): source
                    for source in company.observations
                }
                evidence = [
                    {
                        "quote": quote["quote"],
                        "source_url": sources[quote["observation_id"]].source_url,
                        "occurred_at": None
                        if sources[quote["observation_id"]].occurred_at is None
                        else sources[quote["observation_id"]].occurred_at.isoformat(),
                        "observed_at": None
                        if sources[quote["observation_id"]].observed_at is None
                        else sources[quote["observation_id"]].observed_at.isoformat(),
                    }
                    for quote in item["evidence"]
                ]
                items.append(
                    {
                        "id": item["recommendation_id"],
                        "company": {
                            "id": str(company.company_id),
                            "name": company.name,
                            "domain": company.domain,
                            "country": company.country,
                            "business_sector": None
                            if company.business_sector is None
                            else list(company.business_sector),
                            "company_scale": company.company_scale,
                        },
                        **{
                            key: item[key]
                            for key in (
                                "score",
                                "confidence",
                                "selection_type",
                                "rationale",
                                "unknowns",
                                "breakdown",
                            )
                        },
                        "evidence": evidence,
                    }
                )
            batch_id = uuid4()
            batch = {
                "id": str(batch_id),
                "strategy_id": str(strategy_id),
                "created_at": now.isoformat(),
                "algorithm_version": result.selection.version,
                "assessment_method": "topic-overlap-v1",
                "candidate_count": len(assessments),
                "retrieval_limit": 200,
                "items": items,
            }
            repository.save_batch(
                user_id,
                batch_id,
                strategy_id,
                now,
                _dump({"batch": batch, "ranking": snapshot}),
            )
            work.commit()
        logger.info("Recommendation batch saved with %s selected", len(items))
        return batch

    def get(self, user_id, batch_id):
        with self._uow() as work:
            value = self._repository(work).get_batch(user_id, batch_id)
            if value is None:
                raise NotFoundError("Recommendation batch not found")
            return json.loads(value)["batch"]

    def latest(self, user_id, strategy_id):
        with self._uow() as work:
            value = self._repository(work).latest_batch(user_id, strategy_id)
            if value is None:
                raise NotFoundError("Recommendation batch not found")
            return json.loads(value)["batch"]

    def feedback(self, user_id, batch_id):
        with self._uow() as work:
            repository = self._repository(work)
            if repository.get_batch(user_id, batch_id) is None:
                raise NotFoundError("Recommendation batch not found")
            return [
                json.loads(value) for value in repository.feedback(user_id, batch_id)
            ]

    def review(
        self, user_id, batch_id, recommendation_id, feedback: RecommendationFeedback
    ):
        with self._uow() as work:
            repository = self._repository(work)
            value = repository.get_batch(user_id, batch_id)
            if value is None or recommendation_id not in {
                item["id"] for item in json.loads(value)["batch"]["items"]
            }:
                raise NotFoundError("Recommendation not found")
            now = self._clock()
            feedback_id = uuid4()
            result = {
                "id": str(feedback_id),
                "batch_id": str(batch_id),
                "recommendation_id": recommendation_id,
                "created_at": now.isoformat(),
                **asdict(feedback),
            }
            result["reasons"] = list(result["reasons"])
            repository.append_feedback(
                user_id, batch_id, feedback_id, recommendation_id, now, _dump(result)
            )
            work.commit()
        logger.info("Recommendation feedback appended")
        return result
