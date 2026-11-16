from dataclasses import FrozenInstanceError
from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.domain.entities.business import Business


def test_business_profile_fields_are_unset_until_owner_supplies_them():
    now = datetime.now(UTC)
    business = Business(
        id=uuid4(),
        owner_user_id=uuid4(),
        name=None,
        tagline=None,
        website=None,
        location=None,
        description=None,
        capabilities=None,
        created_at=now,
        updated_at=now,
    )

    assert business.name is None
    assert business.tagline is None
    assert business.website is None
    assert business.location is None
    assert business.description is None
    assert business.capabilities is None
    with pytest.raises(FrozenInstanceError):
        business.name = "Copied from the personal profile"


def test_business_repository_contract_resolves_only_the_owning_user():
    from huginn.management.persistence.contracts.repositories.business import (
        BusinessRepository,
    )

    assert getattr(BusinessRepository, "_is_protocol", False)
    assert {
        "get_by_id",
        "get_by_owner_user_id",
        "create",
        "update",
    } <= set(BusinessRepository.__dict__)
