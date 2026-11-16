from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.prospect_activity import ProspectActivity
from huginn.management.domain.value_objects.command_identity import CommandIdentity


class ProspectActivityRepository(Protocol):
    def get_owned(
        self, business_id: UUID, prospect_id: UUID, activity_id: UUID
    ) -> ProspectActivity | None: ...

    def list_owned(
        self, business_id: UUID, prospect_id: UUID
    ) -> tuple[ProspectActivity, ...]: ...
    def append_once(
        self,
        business_id: UUID,
        prospect_id: UUID,
        identity: CommandIdentity,
        activity: ProspectActivity,
    ) -> ProspectActivity:
        """Deduplicate by Business-scoped request key and verify fingerprint on replay.

        Origin activities additionally use the exact origin uniqueness key so
        another retry key cannot create a second logical save event.
        """
        ...
