"""Frozen inputs read for one attribute assessment."""

from __future__ import annotations

from dataclasses import dataclass

from huginn.elt.gold.models.company_attributes import CompanyAttributes
from huginn.elt.gold.models.source_fact import SourceFact


@dataclass(frozen=True)
class AssessmentSnapshot:
    companies: tuple[CompanyAttributes, ...]
    facts: tuple[SourceFact, ...]
    scope: str
