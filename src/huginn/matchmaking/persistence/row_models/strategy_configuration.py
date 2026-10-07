"""Private joined strategy row, preserving invalid criterion shapes."""

from dataclasses import dataclass
from uuid import UUID

from huginn.matchmaking.application.read_models.strategy_configuration import (
    StrategyConfiguration,
)
from huginn.matchmaking.persistence.errors.database import DataIntegrityError
from huginn.matchmaking.persistence.row_models.json_value import freeze_json_value


@dataclass(frozen=True)
class StrategyConfigurationRow:
    strategy_id: UUID
    user_id: UUID
    name: str
    service_offering_id: UUID
    icp_id: UUID
    offering_row_id: UUID | None
    icp_row_id: UUID | None
    industries: object
    company_sizes: object
    geographies: object
    exclusions: object

    def __post_init__(self) -> None:
        for identifier in (
            self.strategy_id,
            self.user_id,
            self.service_offering_id,
            self.icp_id,
        ):
            if not isinstance(identifier, UUID):
                raise DataIntegrityError("Invalid strategy identifier")
        for sentinel in (self.offering_row_id, self.icp_row_id):
            if sentinel is not None and not isinstance(sentinel, UUID):
                raise DataIntegrityError("Invalid strategy reference")
        if type(self.name) is not str or not self.name or self.name.isspace():
            raise DataIntegrityError("Invalid strategy name")
        if self.name[0].isspace() or self.name[-1].isspace():
            raise DataIntegrityError("Invalid strategy name")

    def to_read_model(self) -> StrategyConfiguration:
        if (
            self.offering_row_id != self.service_offering_id
            or self.icp_row_id != self.icp_id
        ):
            raise DataIntegrityError("Broken strategy reference")
        return StrategyConfiguration(
            self.strategy_id,
            self.user_id,
            self.name,
            self.service_offering_id,
            self.icp_id,
            freeze_json_value(self.industries),
            freeze_json_value(self.company_sizes),
            freeze_json_value(self.geographies),
            freeze_json_value(self.exclusions),
        )
