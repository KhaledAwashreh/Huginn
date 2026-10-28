"""Append-only user judgment of a recommendation, docs/research-ranking.md."""

from dataclasses import dataclass

from huginn.management.domain.errors.errors import ValidationDomainError


@dataclass(frozen=True)
class RecommendationFeedback:
    usefulness: str
    reasons: tuple[str, ...] = ()
    correction: str = ""
    next_step: str = "none"
    outcome: str = "unknown"
    notes: str = ""

    def __post_init__(self):
        choices = (
            (self.usefulness, {"useful", "not_useful", "unsure"}),
            (self.next_step, {"research", "contact", "save", "skip", "none"}),
            (
                self.outcome,
                {
                    "not_contacted",
                    "contacted",
                    "replied",
                    "meeting",
                    "won",
                    "not_relevant",
                    "unknown",
                },
            ),
        )
        if any(
            type(value) is not str or value not in allowed for value, allowed in choices
        ):
            raise ValidationDomainError("Invalid recommendation feedback choice")
        allowed = {
            "service_fit",
            "company_fit",
            "timing",
            "geography",
            "evidence_wrong",
            "customer_not_buyer",
            "already_known",
            "other",
        }
        if (
            type(self.reasons) is not tuple
            or len(self.reasons) > 8
            or any(
                type(reason) is not str or reason not in allowed
                for reason in self.reasons
            )
            or len(set(self.reasons)) != len(self.reasons)
        ):
            raise ValidationDomainError("Invalid feedback reasons")
        if (
            type(self.correction) is not str
            or len(self.correction) > 2000
            or type(self.notes) is not str
            or len(self.notes) > 4000
        ):
            raise ValidationDomainError("Feedback text exceeds limits")
