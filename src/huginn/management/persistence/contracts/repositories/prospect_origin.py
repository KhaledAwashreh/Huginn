from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.prospect_origin import ProspectOrigin
from huginn.management.domain.value_objects.origin_append_result import (
    OriginAppendResult,
)


class ProspectOriginRepository(Protocol):
    def list_for_prospects(
        self, business_id: UUID, prospect_ids: tuple[UUID, ...]
    ) -> tuple[ProspectOrigin, ...]: ...
    def list_owned(
        self, business_id: UUID, prospect_id: UUID
    ) -> tuple[ProspectOrigin, ...]: ...
    def append_if_absent(self, origin: ProspectOrigin) -> OriginAppendResult:
        """Use exact Business/recommendation/revision/prospect identity, not retry key.

        Validate that the recommendation and revision belong to this Business
        and Company. A new historical origin can be added without changing an
        existing Prospect stage; `created` gates the one logical origin activity.
        """
        ...
