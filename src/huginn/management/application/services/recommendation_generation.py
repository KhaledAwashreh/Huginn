"""Generate Business-owned recommendation revisions; ADR-0019, sections 9–10."""

import json
import logging
from collections.abc import Callable
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from huginn.management.application.errors.errors import RateLimitError
from huginn.management.application.policies.recommendation_company_facts import (
    snapshot_recommendation_company,
)
from huginn.management.application.policies.recommendation_generation_retry import (
    generation_retry_after,
)
from huginn.management.application.policies.recommendation_geography import (
    resolve_country_evidence,
)
from huginn.management.application.policies.recommendation_profile_validation import (
    validated_profile_inputs,
)
from huginn.management.application.policies.weekly_match_selection import (
    select_weekly_matches,
)
from huginn.management.application.protocols.recommendation_generation import (
    RecommendationGenerationSource,
)
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
from huginn.management.application.responses.generate_recommendations_response import (
    GenerateRecommendationsResponse,
)
from huginn.management.application.services.release_expired_preparing_offers import (
    release_expired_preparing_offers,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.entities.command_receipt import CommandReceipt
from huginn.management.domain.entities.recommendation import Recommendation
from huginn.management.domain.errors.errors import NotFoundError, ValidationDomainError
from huginn.management.domain.policies.command_fingerprint import (
    fingerprint_command_payload,
)
from huginn.management.domain.value_objects.command_identity import CommandIdentity
from huginn.management.domain.value_objects.common import Principal
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.domain.value_objects.recommendation_status import (
    RecommendationStatus,
)
from huginn.management.domain.value_objects.strategy_assessment_snapshot import (
    StrategyAssessmentSnapshot,
)
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.contracts.prospecting_unit_of_work import (
    ProspectingUnitOfWork,
)
from huginn.matchmaking.application.requests.research_ranking_request import (
    ResearchRankingRequest,
)
from huginn.matchmaking.application.serializers.research_ranking import (
    serialize_research_ranking,
)
from huginn.matchmaking.application.services.research_ranking_service import (
    ResearchRankingService,
)
from huginn.matchmaking.domain.constants.research_ranking import (
    RESEARCH_RANKING_VERSION,
)
from huginn.matchmaking.domain.policies.business_company_fit import assess_company_fit
from huginn.matchmaking.domain.policies.lexical_research import (
    assess_topic_overlap,
)
from huginn.matchmaking.domain.policies.recommendation_eligibility import (
    assess_recommendation_eligibility,
)
from huginn.matchmaking.domain.value_objects.ranking_evidence import RankingEvidence

logger = logging.getLogger(__name__)
_ON_DEMAND_SCOPE = "recommendation_generation:on_demand"
_WEEKLY_SCOPE = "recommendation_generation:weekly"


class RecommendationGenerationService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], ProspectingUnitOfWork],
        *,
        source_factory: Callable[[DatabaseSession], RecommendationGenerationSource],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._source_factory = source_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(
        self, principal: Principal, request: GenerateRecommendationsRequest
    ) -> GenerateRecommendationsResponse:
        if not isinstance(principal, Principal):
            raise ValidationDomainError("Authenticated Principal required")
        return self._execute(
            owner_user_id=principal.user_id,
            business_id=None,
            strategy_id=request.strategy_id,
            limit=request.limit,
            weekly=False,
            assessed_by_user_id=principal.user_id,
        )

    def execute_weekly(self, business_id: UUID) -> GenerateRecommendationsResponse:
        if not isinstance(business_id, UUID):
            raise ValidationDomainError("Business ID required")
        return self._execute(
            owner_user_id=None,
            business_id=business_id,
            strategy_id=None,
            limit=7,
            weekly=True,
            assessed_by_user_id=None,
        )

    def _execute(
        self,
        *,
        owner_user_id: UUID | None,
        business_id: UUID | None,
        strategy_id: UUID | None,
        limit: int,
        weekly: bool,
        assessed_by_user_id: UUID | None,
    ) -> GenerateRecommendationsResponse:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("Recommendation generation clock must be timezone-aware")
        with self._uow_factory() as work:
            if business_id is None:
                business = work.businesses.get_by_owner_user_id(owner_user_id)
                if business is None:
                    raise NotFoundError("Business not found")
                business_id = business.id
            else:
                business = work.businesses.get_by_id(business_id)
                if business is None:
                    raise NotFoundError("Business not found")
            owner_user_id = business.owner_user_id

        release_expired_preparing_offers(
            self._uow_factory, business_id, clock=self._clock
        )

        with self._uow_factory() as work:
            business = work.businesses.get_by_id(business_id)
            if business is None:
                raise NotFoundError("Business not found")
            owner_user_id = business.owner_user_id
            connection = work.connection
            if connection is None:
                raise RuntimeError("Recommendation generation UOW has no connection")
            source = self._source_factory(connection)
            if not weekly:
                source.lock_successful_run_window(business_id)
                successful = source.successful_on_demand_runs_since(
                    business_id, now - timedelta(minutes=15)
                )
                retry_after = generation_retry_after(successful, now)
                if retry_after:
                    raise RateLimitError(
                        "Recommendation generation limit reached", retry_after
                    )
                profiles = (source.profile(owner_user_id, strategy_id),)
                if profiles[0] is None:
                    raise NotFoundError("Active strategy not found")
            else:
                profiles = source.active_profiles(owner_user_id)
                if not profiles:
                    raise NotFoundError("No valid active strategy found")

            validated_profiles = []
            for profile in profiles:
                if profile is None:
                    continue
                try:
                    validated_profile_inputs(profile)
                except ValidationDomainError:
                    if weekly:
                        logger.warning(
                            "Weekly recommendation generation skipped invalid strategy %s",
                            profile.strategy_id,
                        )
                        continue
                    raise
                validated_profiles.append(profile)
            if not validated_profiles:
                raise NotFoundError("No valid active strategy found")

            contexts: dict[tuple[UUID, UUID], tuple] = {}
            strategy_items: list[dict] = []
            candidate_count = 0
            for profile in validated_profiles:
                profile_data, terms, service_terms, icp = validated_profile_inputs(
                    profile
                )
                companies, fits, assessments = self._assess_candidates(
                    source,
                    business_id,
                    profile,
                    profile_data,
                    terms,
                    service_terms,
                    icp,
                    now,
                )
                candidate_count += len(assessments)
                profile_data["retrieval_terms"] = list(terms)
                profile_data["service_terms"] = list(service_terms)
                evaluation_seed = f"{profile.strategy_id}/{now.date().isoformat()}"
                ranked = ResearchRankingService().execute(
                    ResearchRankingRequest(
                        str(profile.strategy_id),
                        json.dumps(profile_data, sort_keys=True, allow_nan=False),
                        "topic-overlap-v2",
                        now,
                        20 if weekly else limit,
                        evaluation_seed,
                        tuple(assessments),
                    )
                )
                snapshot = serialize_research_ranking(ranked)
                for item in snapshot["recommendations"]:
                    company_id = UUID(item["company_id"])
                    company = companies[company_id]
                    fit = fits[company_id]
                    enriched = self._display_item(
                        item, profile, profile_data, company, fit
                    )
                    strategy_items.append(enriched)
                    contexts[(company_id, profile.strategy_id)] = (
                        profile,
                        profile_data,
                        company,
                        fit,
                        item,
                        evaluation_seed,
                    )

            selected = (
                select_weekly_matches(strategy_items)[:7]
                if weekly
                else sorted(
                    strategy_items,
                    key=lambda item: item["position"],
                )[:limit]
            )
            run_id = uuid4()
            references = []
            selected_company_ids = sorted(
                {UUID(item["company"]["id"]) for item in selected}, key=str
            )
            for company_id in selected_company_ids:
                work.lock_business_company(business_id, company_id)
            finalization_time = self._clock()
            if (
                finalization_time.tzinfo is None
                or finalization_time.utcoffset() is None
            ):
                raise ValueError(
                    "Recommendation generation clock must be timezone-aware"
                )
            for item in selected:
                company_id = UUID(item["company"]["id"])
                selected_strategies = tuple(
                    UUID(strategy["id"]) for strategy in item["strategies"]
                )
                with_context = [
                    contexts[(company_id, value)] for value in selected_strategies
                ]
                persisted = self._persist_revision(
                    work,
                    source,
                    business_id,
                    company_id,
                    selected_strategies,
                    with_context,
                    now,
                    finalization_time,
                    assessed_by_user_id,
                )
                if persisted is not None:
                    references.append(persisted)

            run_scope = _WEEKLY_SCOPE if weekly else _ON_DEMAND_SCOPE
            response = GenerateRecommendationsResponse(
                business_id,
                run_id,
                tuple(references),
            )
            receipt_key = str(uuid4())
            fingerprint = fingerprint_command_payload(
                run_scope,
                {
                    "business_id": str(business_id),
                    "strategy_id": None if strategy_id is None else str(strategy_id),
                    "limit": limit,
                    "as_of": now.isoformat(),
                },
            )
            work.commands.record(
                CommandReceipt(
                    business_id,
                    run_scope,
                    CommandIdentity(receipt_key, fingerprint),
                    "recommendation_generation_run",
                    run_id,
                    1,
                    JsonSnapshot(
                        {
                            "business_id": str(business_id),
                            "run_id": str(run_id),
                            "mode": "weekly" if weekly else "on_demand",
                            "references": [
                                {
                                    "recommendation_id": str(value.recommendation_id),
                                    "revision_id": str(value.revision_id),
                                    "recommendation_version": value.recommendation_version,
                                }
                                for value in references
                            ],
                            "candidate_count": candidate_count,
                        }
                    ),
                    now,
                )
            )
            work.commit()
            logger.info(
                "Business recommendation generation committed business=%s mode=%s selected=%s",
                business_id,
                run_scope,
                len(references),
            )
            return response

    def _assess_candidates(
        self,
        source: RecommendationGenerationSource,
        business_id: UUID,
        profile: RecommendationProfile,
        profile_data: dict,
        terms: tuple[str, ...],
        service_terms: tuple[str, ...],
        icp: dict,
        now: datetime,
    ) -> tuple[dict, dict, list]:
        companies: dict[UUID, RecommendationCompany] = {}
        fits = {}
        seen = set()
        offset = 0
        cutoff = now - timedelta(days=365)
        while len(companies) < 200:
            page = source.candidates(terms, cutoff, now, 200, offset=offset)
            current_candidates = []
            for raw_company in page:
                if raw_company.company_id in seen:
                    continue
                seen.add(raw_company.company_id)
                current_candidates.append(raw_company)
            company_ids = tuple(company.company_id for company in current_candidates)
            # Clear stale claims for this candidate page before eligibility.
            # This targeted bounded pass prevents an unrelated global backlog
            # from stranding an otherwise eligible Company.
            for start in range(0, len(company_ids), 100):
                release_expired_preparing_offers(
                    self._uow_factory,
                    business_id,
                    clock=self._clock,
                    company_ids=tuple(
                        sorted(company_ids[start : start + 100], key=str)
                    ),
                )
            states = source.company_states(business_id, company_ids, now)
            if len(states) != len(company_ids):
                raise RuntimeError(
                    "Company state projection did not match requested IDs"
                )
            eligible_candidates = []
            for raw_company, state in zip(current_candidates, states, strict=True):
                if not assess_recommendation_eligibility(state, now).eligible:
                    continue
                company = resolve_country_evidence(raw_company)
                fit = assess_company_fit(
                    company.company_id,
                    company.business_sector,
                    company.company_scale,
                    company.country,
                    icp,
                )
                if fit.eligible:
                    eligible_candidates.append((company, fit))
            for company, fit in eligible_candidates:
                companies[company.company_id] = company
                fits[company.company_id] = fit
                if len(companies) == 200:
                    break
            if len(page) < 200:
                break
            offset += 200
        assessments = []
        for company in companies.values():
            company_fit = fits[company.company_id]
            assessment = assess_topic_overlap(
                company.company_id,
                company.observations,
                terms,
                now,
                industry_match=company_fit.industry,
                size_match=company_fit.size,
                country_match=company_fit.country,
                service_terms=service_terms,
            )
            if assessment is None:
                continue
            if company.country_evidence_id:
                label = next(
                    value
                    for identifier, value in company.source_countries
                    if identifier == company.country_evidence_id
                )
                fact = RankingEvidence(
                    company.country_evidence_id, f"category: {label}"
                )
                if fact not in assessment.evidence:
                    assessment = replace(
                        assessment, evidence=assessment.evidence + (fact,)
                    )
            configured = {
                "industry": icp.get("industries"),
                "size": icp.get("company_sizes"),
                "country": icp.get("geographies"),
            }
            unknowns = tuple(
                f"ICP {field} is unverified: source information is missing or unresolved."
                for field, status in company_fit.dimensions.items()
                if status == "unknown" and configured[field]
            )
            assessments.append(
                replace(assessment, unknowns=assessment.unknowns + unknowns)
            )
        return companies, fits, assessments

    @staticmethod
    def _display_item(item, profile, profile_data, company, fit) -> dict:
        return {
            "id": item["recommendation_id"],
            "position": item["position"],
            "icp_fit": dict(fit.dimensions),
            "strategies": [
                {
                    "id": str(profile.strategy_id),
                    "name": profile_data.get("strategy", {}).get(
                        "name", "Discovery strategy"
                    ),
                    "offering": profile_data.get("offering", {}).get(
                        "name", "Service offering"
                    ),
                }
            ],
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
                    "evidence",
                )
            },
        }

    def _persist_revision(
        self,
        work: ProspectingUnitOfWork,
        source: RecommendationGenerationSource,
        business_id: UUID,
        company_id: UUID,
        strategy_ids: tuple[UUID, ...],
        contexts: list[tuple],
        now: datetime,
        finalization_time: datetime,
        assessed_by_user_id: UUID | None,
    ) -> GeneratedRecommendationReference | None:
        cutoff = now - timedelta(days=365)
        if not all(
            source.candidate_is_current(company, cutoff, finalization_time)
            for _, _, company, _, _, _ in contexts
        ):
            return None
        current_states = source.company_states(
            business_id, (company_id,), finalization_time
        )
        if (
            len(current_states) != 1
            or not assess_recommendation_eligibility(
                current_states[0], finalization_time
            ).eligible
        ):
            return None
        recommendation = work.recommendations.get_open(business_id, company_id)
        if recommendation is None:
            recommendation = work.recommendations.create_open(
                Recommendation(
                    uuid4(),
                    business_id,
                    company_id,
                    RecommendationStatus("open"),
                    now,
                    now,
                )
            )
        history = work.assessment_revisions.list_history(business_id, recommendation.id)
        revision_id = uuid4()
        revision_number = (
            max((value.revision_number for value in history), default=0) + 1
        )
        strategy_snapshots = tuple(
            self._strategy_snapshot(
                profile,
                profile_data,
                company,
                fit,
                ranked_item,
                evaluation_seed,
            )
            for profile, profile_data, company, fit, ranked_item, evaluation_seed in contexts
        )
        first_profile = contexts[0][1]
        evidence_snapshots = []
        observation_ids = set()
        for _, _, company, _, ranked_item, _ in contexts:
            source_by_id = {
                str(obs.observation_id): obs for obs in company.observations
            }
            for evidence in ranked_item["evidence"]:
                identifier = UUID(evidence["observation_id"])
                if identifier in observation_ids:
                    continue
                observation_ids.add(identifier)
                observation = source_by_id[str(identifier)]
                evidence_snapshots.append(
                    JsonSnapshot(
                        {
                            "observation_id": str(identifier),
                            "quote": evidence["quote"],
                            "description": observation.description,
                            "source": observation.source,
                            "source_url": observation.source_url,
                            "source_country": dict(company.source_countries).get(
                                identifier
                            ),
                            "occurred_at": _iso(observation.occurred_at),
                            "observed_at": _iso(observation.observed_at),
                        }
                    )
                )
        versions = {
            RESEARCH_RANKING_VERSION,
            "company-fit-v1",
            "topic-overlap-v2",
        }
        revision = AssessmentRevision(
            revision_id,
            recommendation.id,
            business_id,
            company_id,
            revision_number,
            now,
            strategy_snapshots,
            JsonSnapshot(first_profile.get("professional_profile") or {}),
            tuple(evidence_snapshots),
            tuple(sorted(observation_ids, key=str)),
            tuple(sorted(versions)),
            None,
            assessed_by_user_id,
        )
        work.assessment_revisions.append(revision)
        selected = work.recommendations.select_current_revision(
            business_id,
            recommendation.id,
            revision.id,
            recommendation.version,
        )
        return GeneratedRecommendationReference(
            recommendation.id, revision.id, selected.version
        )

    @staticmethod
    def _strategy_snapshot(profile, profile_data, company, fit, item, evaluation_seed):
        strategy = profile_data.get("strategy", {})
        offering = profile_data.get("offering", {})
        icp = profile_data.get("icp", {})
        try:
            offering_id = UUID(str(offering["id"]))
            icp_id = UUID(str(icp["id"]))
        except (KeyError, ValueError) as exc:
            raise ValidationDomainError("Strategy profile IDs are invalid") from exc
        return StrategyAssessmentSnapshot(
            profile.strategy_id,
            offering_id,
            icp_id,
            JsonSnapshot(strategy),
            JsonSnapshot(offering),
            JsonSnapshot(icp),
            JsonSnapshot(
                {
                    "company_id": str(company.company_id),
                    "company_facts": snapshot_recommendation_company(company),
                    "score": item["score"],
                    "confidence": item["confidence"],
                    "selection_type": item["selection_type"],
                    "rationale": item["rationale"],
                    "unknowns": item["unknowns"],
                    "breakdown": item["breakdown"],
                    "icp_fit": dict(fit.dimensions),
                    "evidence": item["evidence"],
                    "evaluation_seed": evaluation_seed,
                }
            ),
        )


def _iso(value: datetime | None) -> str | None:
    return None if value is None else value.isoformat()
