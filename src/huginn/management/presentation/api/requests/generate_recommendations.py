from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt


class GenerateRecommendationsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    strategy_id: UUID
    limit: Annotated[StrictInt, Field(ge=1, le=20)] = 10
