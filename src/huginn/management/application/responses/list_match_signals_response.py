"""Current company signal page returned by the use case."""

from dataclasses import dataclass

from huginn.management.application.read_models.current_company_signal import (
    CurrentCompanySignal,
)
from huginn.management.domain.value_objects.common import Page


@dataclass(frozen=True, slots=True)
class ListMatchSignalsResponse:
    page: Page[CurrentCompanySignal]
