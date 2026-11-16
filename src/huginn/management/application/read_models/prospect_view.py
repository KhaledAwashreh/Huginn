"""Current pursuit state with its exact retained assessment origins."""

from dataclasses import dataclass

from huginn.management.application.read_models.current_company import CurrentCompany
from huginn.management.application.read_models.current_source_context import (
    CurrentSourceContext,
)
from huginn.management.application.read_models.prospect_origin_view import (
    ProspectOriginView,
)
from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.entities.prospect_activity import ProspectActivity


@dataclass(frozen=True, slots=True)
class ProspectView:
    prospect: Prospect
    company: CurrentCompany
    origins: tuple[ProspectOriginView, ...]
    activities: tuple[ProspectActivity, ...] | None = None
    current_source_context: CurrentSourceContext | None = None
