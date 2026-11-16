import pytest

from huginn.management.domain.errors.errors import ValidationDomainError
from huginn.management.domain.value_objects.recommendation_feedback import (
    RecommendationFeedback,
)


def test_feedback_rejects_unknown_values_and_mutable_or_oversized_inputs():
    for kwargs in (
        {"usefulness": "bad"},
        {"usefulness": "useful", "reasons": ["service_fit"]},
        {"usefulness": "useful", "reasons": ("invented",)},
        {"usefulness": "useful", "correction": "x" * 2001},
    ):
        with pytest.raises(ValidationDomainError):
            RecommendationFeedback(**kwargs)
