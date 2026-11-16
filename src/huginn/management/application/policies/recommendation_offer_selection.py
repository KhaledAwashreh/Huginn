"""Pure validation that a selected revision still describes current inputs."""

import json
from uuid import UUID

from huginn.management.application.policies.recommendation_company_facts import (
    snapshot_recommendation_company,
)
from huginn.management.application.read_models.recommendation_company import (
    RecommendationCompany,
)
from huginn.management.application.read_models.recommendation_profile import (
    RecommendationProfile,
)
from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.matchmaking.domain.policies.business_company_fit import assess_company_fit


def offer_selection_inputs_match(
    revision: AssessmentRevision,
    company: RecommendationCompany,
    profiles: dict[UUID, RecommendationProfile],
) -> bool:
    company_facts = snapshot_recommendation_company(company)
    for assessment in revision.strategy_assessments:
        snapshot = assessment.assessment_snapshot.to_json_object()
        if snapshot.get("company_facts") != company_facts:
            return False
        profile = profiles.get(assessment.strategy_id)
        if profile is None:
            return False
        try:
            current = json.loads(profile.snapshot_json)
        except TypeError, ValueError:
            return False
        if (
            current.get("strategy") != assessment.strategy_snapshot.to_json_object()
            or current.get("offering") != assessment.offering_snapshot.to_json_object()
            or current.get("icp")
            != assessment.ideal_client_profile_snapshot.to_json_object()
            or (current.get("professional_profile") or {})
            != revision.professional_profile_snapshot.to_json_object()
        ):
            return False
        fit = assess_company_fit(
            company.company_id,
            company.business_sector,
            company.company_scale,
            company.country,
            assessment.ideal_client_profile_snapshot.to_json_object(),
        )
        if not fit.eligible or dict(fit.dimensions) != snapshot.get("icp_fit"):
            return False
    return bool(revision.strategy_assessments)
