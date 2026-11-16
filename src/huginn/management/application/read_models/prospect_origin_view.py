"""Exact explanation associated with a recorded Save."""

from dataclasses import dataclass

from huginn.management.domain.entities.assessment_revision import AssessmentRevision
from huginn.management.domain.entities.prospect_origin import ProspectOrigin
from huginn.management.domain.entities.recommendation import Recommendation


@dataclass(frozen=True, slots=True)
class ProspectOriginView:
    origin: ProspectOrigin
    recommendation: Recommendation
    assessment: AssessmentRevision
