"""Structured output from an attribute assessment."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class AssessmentResult:
    summary: dict[str, object]
    receipts: tuple[dict[str, object], ...]
