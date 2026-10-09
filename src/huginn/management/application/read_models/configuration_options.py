"""Collected Gold criterion option projection."""

from dataclasses import dataclass

from huginn.management.application.read_models.configuration_option import (
    ConfigurationOption,
)


@dataclass(frozen=True)
class ConfigurationOptions:
    industries: tuple[ConfigurationOption, ...]
    countries: tuple[ConfigurationOption, ...]
    company_sizes: tuple[ConfigurationOption, ...]
