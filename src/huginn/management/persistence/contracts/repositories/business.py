"""Business ownership persistence contract."""

from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.business import Business
from huginn.management.domain.value_objects.business_changes import BusinessChanges
from huginn.management.domain.value_objects.new_business import NewBusiness


class BusinessRepository(Protocol):
    def get_by_id(self, business_id: UUID) -> Business | None: ...
    def get_by_id_for_update(self, business_id: UUID) -> Business | None: ...
    def get_by_owner_user_id(self, owner_user_id: UUID) -> Business | None: ...
    def create(self, business: NewBusiness) -> Business: ...
    def update(
        self, business_id: UUID, changes: BusinessChanges
    ) -> Business | None: ...
