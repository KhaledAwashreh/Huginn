"""Confirm actual display using the exact preparation capability."""

from typing import Annotated

from pydantic import Field

from huginn.management.presentation.api.requests.common import RequestModel


class ConfirmRecommendationOfferRequest(RequestModel):
    claim_token: Annotated[str, Field(min_length=1)]
