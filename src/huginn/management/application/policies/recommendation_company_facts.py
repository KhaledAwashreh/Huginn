"""Stable snapshot shape for the Company facts actually used in assessment."""

from huginn.management.application.read_models.recommendation_company import (
    RecommendationCompany,
)


def snapshot_recommendation_company(company: RecommendationCompany) -> dict:
    country_label = (
        None
        if company.country_evidence_id is None
        else dict(company.source_countries).get(company.country_evidence_id)
    )
    return {
        "company_id": str(company.company_id),
        "name": company.name,
        "domain": company.domain,
        "business_sector": None
        if company.business_sector is None
        else list(company.business_sector),
        "raw_country": company.source_country_value
        if company.country_evidence_id is not None
        else company.country,
        "resolved_country": company.country,
        "country_evidence_id": None
        if company.country_evidence_id is None
        else str(company.country_evidence_id),
        "country_evidence_label": country_label,
        "company_scale": company.company_scale,
    }
