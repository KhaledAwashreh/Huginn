from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

type FeedbackReason = Literal[
    "service_fit",
    "company_fit",
    "timing",
    "geography",
    "evidence_wrong",
    "customer_not_buyer",
    "already_known",
    "other",
]


class RecommendationFeedbackRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    recommendation_id: Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]
    usefulness: Literal["useful", "not_useful", "unsure"]
    reasons: Annotated[list[FeedbackReason], Field(max_length=8)] = Field(
        default_factory=list
    )
    correction: Annotated[str, Field(max_length=2000)] = ""
    next_step: Literal["research", "contact", "save", "skip", "none"] = "none"
    outcome: Literal[
        "not_contacted",
        "contacted",
        "replied",
        "meeting",
        "won",
        "not_relevant",
        "unknown",
    ] = "unknown"
    notes: Annotated[str, Field(max_length=4000)] = ""
