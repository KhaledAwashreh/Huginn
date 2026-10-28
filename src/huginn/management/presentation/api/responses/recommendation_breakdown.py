from pydantic import BaseModel


class RecommendationBreakdownResponse(BaseModel):
    service_fit: int
    business_context: int
    company_preferences: int
    timing: int
