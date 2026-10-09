"""Collected Gold criterion value and company coverage."""

from dataclasses import dataclass


@dataclass(frozen=True)
class ConfigurationOption:
    value: str
    company_count: int
