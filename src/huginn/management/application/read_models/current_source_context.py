"""Guarded current source context, independent of retained fit assessments."""

from dataclasses import dataclass
from typing import Literal

from huginn.management.application.read_models.current_company_signal import (
    CurrentCompanySignal,
)


@dataclass(frozen=True, slots=True)
class CurrentSourceContext:
    signals: tuple[CurrentCompanySignal, ...]
    has_more: bool
    evidence_state: Literal["current", "changed", "unavailable", "not_assessed"]
