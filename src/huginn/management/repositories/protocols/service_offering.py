"""Service offering persistence contract."""

from typing import Protocol
from uuid import UUID

from huginn.management.domain.common import Page
from huginn.management.domain.service_offering import (
    NewServiceOffering,
    ServiceOffering,
    ServiceOfferingChanges,
)


class ServiceOfferingRepository(Protocol):
    def create(self, offering: NewServiceOffering) -> ServiceOffering: ...
    def get_owned(self, user_id: UUID, offering_id: UUID) -> ServiceOffering | None: ...
    def list_owned(
        self, user_id: UUID, *, limit: int, offset: int
    ) -> Page[ServiceOffering]: ...
    def update_owned(
        self, user_id: UUID, offering_id: UUID, changes: ServiceOfferingChanges
    ) -> ServiceOffering | None: ...
    def delete_owned(self, user_id: UUID, offering_id: UUID) -> bool: ...
