"""Validate a frozen strategy input identically before reservation and assessment."""

import json

from huginn.management.application.policies.recommendation_preferences import (
    validate_exclusions,
    validate_icp_filters,
)
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.matchmaking.domain.policies.lexical_research import offering_terms


def validated_profile_inputs(profile):
    data = json.loads(profile.snapshot_json)
    terms = offering_terms(profile.offering_text)
    if not terms:
        raise ValidationDomainError(
            "Offering needs descriptive topics before generating recommendations"
        )
    icp = data.get("icp", {})
    validate_exclusions(icp.get("exclusions", []))
    validate_icp_filters(icp)
    service_terms = offering_terms(data.get("offering", {}).get("name", "")) or terms
    return data, terms, service_terms, icp
