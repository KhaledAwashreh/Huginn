"""Private response and bounded query dependencies for workflow reads."""

from typing import Annotated

from fastapi import Query, Response

from huginn.management.application.requests.list_prospecting_request import (
    ListProspectingRequest,
)


def private_prospecting_response(response: Response) -> None:
    response.headers["Cache-Control"] = "no-store"
    response.headers["Vary"] = "Cookie"


def prospecting_page(
    search: Annotated[str, Query(max_length=200)] = "",
    offset: Annotated[int, Query(ge=0, le=2**63 - 1)] = 0,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
) -> ListProspectingRequest:
    return ListProspectingRequest(search=search, offset=offset, limit=limit)
