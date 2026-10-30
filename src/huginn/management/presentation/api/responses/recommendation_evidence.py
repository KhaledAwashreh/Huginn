from datetime import datetime

from pydantic import BaseModel


class RecommendationEvidenceResponse(BaseModel):
    quote: str
    source_url: str
    occurred_at: datetime | None
    observed_at: datetime | None
