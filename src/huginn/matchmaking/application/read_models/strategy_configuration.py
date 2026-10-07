from dataclasses import dataclass
from uuid import UUID

from huginn.matchmaking.domain.types.json_value import RawJsonValue


@dataclass(frozen=True)
class StrategyConfiguration:
    strategy_id: UUID
    user_id: UUID
    name: str
    service_offering_id: UUID
    icp_id: UUID
    industries: RawJsonValue
    company_sizes: RawJsonValue
    geographies: RawJsonValue
    exclusions: RawJsonValue
