"""Strict database boundary for one owner's durable run result."""

from typing import Literal, Self

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator

EvaluationState = Literal[
    "pending",
    "running",
    "succeeded",
    "disabled_user",
    "user_not_found",
    "failed",
    "commit_outcome_unknown",
    "not_executed",
]


class EvaluationSummaryRow(BaseModel):
    model_config = ConfigDict(strict=True, extra="forbid", frozen=True)
    state: EvaluationState
    requested_at: AwareDatetime
    started_at: AwareDatetime | None
    finished_at: AwareDatetime | None
    cutoff: AwareDatetime
    as_of: AwareDatetime
    tracking_stale: bool
    strategies_evaluated: int | None = Field(default=None, ge=0)
    strategies_skipped: int | None = Field(default=None, ge=0)
    created_matches_count: int | None = Field(default=None, ge=0)
    existing_matches_skipped_count: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def counts_only_for_succeeded(self) -> Self:
        values = (
            self.strategies_evaluated,
            self.strategies_skipped,
            self.created_matches_count,
            self.existing_matches_skipped_count,
        )
        if self.state == "succeeded" and any(value is None for value in values):
            raise ValueError("succeeded result requires all acknowledged counts")
        if self.state != "succeeded" and any(value is not None for value in values):
            raise ValueError("non-success result cannot expose counts")
        return self
