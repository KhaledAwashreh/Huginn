"""Management runtime configuration defined by ADR-0011."""

import os
from dataclasses import dataclass, field

from dotenv import load_dotenv


@dataclass(frozen=True)
class ManagementConfig:
    """Management process configuration defined by ADR-0011."""

    database_url: str = field(repr=False)


def load_config() -> ManagementConfig:
    """Load the isolated management configuration defined by ADR-0011."""
    load_dotenv()
    value = os.environ.get("HUGINN_MANAGEMENT_DATABASE_URL")
    if not value or not value.strip():
        raise RuntimeError("HUGINN_MANAGEMENT_DATABASE_URL is not set")
    return ManagementConfig(database_url=value)
