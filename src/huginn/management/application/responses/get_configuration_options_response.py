"""Collected definition choices, not combined match predictions."""

from dataclasses import dataclass

from huginn.management.application.read_models.configuration_option import (
    ConfigurationOption,
)


@dataclass(frozen=True)
class GetConfigurationOptionsResponse:
    industries: tuple[ConfigurationOption, ...]
    countries: tuple[ConfigurationOption, ...]
    company_sizes: tuple[ConfigurationOption, ...]
