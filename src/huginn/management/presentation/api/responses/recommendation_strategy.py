from uuid import UUID

from pydantic import BaseModel


class RecommendationStrategyResponse(BaseModel):
    id: UUID
    name: str
    offering: str
