"""Committed result for a manual prospect command."""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from huginn.management.domain.entities.prospect import Prospect
from huginn.management.domain.entities.prospect_activity import ProspectActivity
from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.activity_kind import ActivityKind
from huginn.management.domain.value_objects.json_snapshot import JsonSnapshot
from huginn.management.domain.value_objects.prospect_stage import ProspectStage


@dataclass(frozen=True, slots=True)
class ProspectCommandResponse:
    prospect: Prospect
    activity: ProspectActivity

    def __post_init__(self) -> None:
        if not isinstance(self.prospect, Prospect) or not isinstance(
            self.activity, ProspectActivity
        ):
            raise ValidationDomainError(
                "Prospect command result needs state and activity"
            )
        if (self.prospect.business_id, self.prospect.id) != (
            self.activity.business_id,
            self.activity.prospect_id,
        ):
            raise ValidationDomainError(
                "Activity does not belong to the returned prospect"
            )

    def snapshot(self) -> JsonSnapshot:
        return JsonSnapshot(
            {
                "prospect": {
                    "id": str(self.prospect.id),
                    "business_id": str(self.prospect.business_id),
                    "company_id": str(self.prospect.company_id),
                    "stage": self.prospect.stage.value,
                    "created_at": self.prospect.created_at.isoformat(),
                    "updated_at": self.prospect.updated_at.isoformat(),
                    "version": self.prospect.version,
                    "notes": self.prospect.notes,
                    "follow_up_at": _iso(self.prospect.follow_up_at),
                    "last_active_stage": self.prospect.last_active_stage.value
                    if self.prospect.last_active_stage
                    else None,
                },
                "activity": {
                    "id": str(self.activity.id),
                    "business_id": str(self.activity.business_id),
                    "prospect_id": str(self.activity.prospect_id),
                    "actor_user_id": str(self.activity.actor_user_id),
                    "kind": self.activity.kind.value,
                    "occurred_at": self.activity.occurred_at.isoformat(),
                    "recorded_at": self.activity.recorded_at.isoformat(),
                    "payload": self.activity.payload.to_json_object(),
                    "correction_of_id": str(self.activity.correction_of_id)
                    if self.activity.correction_of_id
                    else None,
                },
            }
        )

    @classmethod
    def from_snapshot(cls, snapshot: JsonSnapshot) -> ProspectCommandResponse:
        prospect = snapshot.value["prospect"]
        activity = snapshot.value["activity"]
        return cls(
            Prospect(
                UUID(str(prospect["id"])),
                UUID(str(prospect["business_id"])),
                UUID(str(prospect["company_id"])),
                ProspectStage(prospect["stage"]),
                datetime.fromisoformat(prospect["created_at"]),
                datetime.fromisoformat(prospect["updated_at"]),
                prospect["version"],
                prospect["notes"],
                datetime.fromisoformat(prospect["follow_up_at"])
                if prospect["follow_up_at"]
                else None,
                ProspectStage(prospect["last_active_stage"])
                if prospect["last_active_stage"]
                else None,
            ),
            ProspectActivity(
                UUID(str(activity["id"])),
                UUID(str(activity["business_id"])),
                UUID(str(activity["prospect_id"])),
                UUID(str(activity["actor_user_id"])),
                ActivityKind(activity["kind"]),
                datetime.fromisoformat(activity["occurred_at"]),
                datetime.fromisoformat(activity["recorded_at"]),
                activity["payload"],
                UUID(str(activity["correction_of_id"]))
                if activity["correction_of_id"]
                else None,
            ),
        )


def _iso(value: datetime | None) -> str | None:
    return value.isoformat() if value else None
