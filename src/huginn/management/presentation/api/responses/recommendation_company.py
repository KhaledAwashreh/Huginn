from uuid import UUID

from pydantic import BaseModel


class RecommendationCompanyResponse(BaseModel):
    id: UUID
    name: str
    domain: str
    country: str | None = None
    business_sector: list[str] | None = None
    company_scale: str | None = None
