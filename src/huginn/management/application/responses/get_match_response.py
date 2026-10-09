"""Owned match returned by the detail use case."""

from dataclasses import dataclass

from huginn.management.application.read_models.user_match import UserMatch


@dataclass(frozen=True, slots=True)
class GetMatchResponse:
    match: UserMatch
