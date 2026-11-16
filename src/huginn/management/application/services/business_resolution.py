"""Resolve a signed-in person to their sole Business."""

from uuid import UUID

from huginn.management.domain.errors.errors import NotFoundError
from huginn.management.domain.value_objects.common import Principal
from huginn.management.persistence.contracts.repositories.business import (
    BusinessRepository,
)


def business_id_for_principal(
    principal: Principal, businesses: BusinessRepository
) -> UUID:
    business = businesses.get_by_owner_user_id(principal.user_id)
    if business is None:
        raise NotFoundError("Business not found")
    return business.id
