"""Report-only feedback choices, independent of pursuit commands."""

from typing import Annotated, Literal

from pydantic import Field

from huginn.management.presentation.api.requests.common import RequestModel
from huginn.management.presentation.api.requests.recommendation_feedback import (
    FeedbackReason,
)


class RecommendationQualityFeedbackRequest(RequestModel):
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
