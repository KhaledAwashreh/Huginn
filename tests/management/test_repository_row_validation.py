from datetime import UTC, datetime
from uuid import uuid4

import pytest
from pydantic import ValidationError

from huginn.management.repositories.postgres.discovery_strategy import (
    PostgresClientDiscoveryStrategyRepository,
)
from huginn.management.repositories.postgres.ideal_client_profile import (
    PostgresIdealClientProfileRepository,
)
from huginn.management.repositories.postgres.professional_profile import (
    PostgresProfessionalProfileRepository,
)


def test_icp_mapper_rejects_malformed_persisted_jsonb_item():
    now = datetime.now(UTC)
    row = (
        uuid4(),
        uuid4(),
        "Target",
        ({"unexpected": True},),
        (),
        (),
        (),
        now,
        now,
    )

    with pytest.raises(ValidationError):
        PostgresIdealClientProfileRepository._map(row)


def test_icp_mapper_returns_normalized_persisted_strings():
    now = datetime.now(UTC)
    row = (
        uuid4(),
        uuid4(),
        "  Target  ",
        ({"name": "  SaaS  "},),
        ({"band": "11-100"},),
        ({"kind": "country", "value": "  Germany  "},),
        (),
        now,
        now,
    )

    profile = PostgresIdealClientProfileRepository._map(row)

    assert profile.name == "Target"
    assert profile.industries == ({"name": "SaaS"},)
    assert profile.geographies == ({"kind": "country", "value": "Germany"},)


def test_professional_profile_mapper_rejects_malformed_persisted_experience():
    now = datetime.now(UTC)
    row = (
        uuid4(),
        uuid4(),
        None,
        None,
        (),
        ({"organization": "Acme"},),
        (),
        now,
        now,
    )

    with pytest.raises(ValidationError):
        PostgresProfessionalProfileRepository._map(row)


def test_strategy_mapper_rejects_invalid_persisted_name():
    now = datetime.now(UTC)
    row = (uuid4(), uuid4(), " ", uuid4(), uuid4(), False, now, now)

    with pytest.raises(ValidationError):
        PostgresClientDiscoveryStrategyRepository._map(row)


def test_strategy_mapper_returns_normalized_persisted_name():
    now = datetime.now(UTC)
    row = (uuid4(), uuid4(), "  Strategy  ", uuid4(), uuid4(), False, now, now)

    assert PostgresClientDiscoveryStrategyRepository._map(row).name == "Strategy"
