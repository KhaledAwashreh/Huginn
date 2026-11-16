import pytest

from huginn.management.application.requests.list_prospecting_request import (
    ListProspectingRequest,
)
from huginn.management.domain.errors.errors import ValidationDomainError


@pytest.mark.parametrize(
    "values",
    [
        {"limit": 0},
        {"limit": 101},
        {"limit": True},
        {"offset": -1},
        {"offset": 2**63},
        {"offset": False},
        {"search": None},
        {"search": "x" * 201},
    ],
)
def test_read_requests_reject_invalid_paging_and_search(values):
    with pytest.raises(ValidationDomainError):
        ListProspectingRequest(**values)


def test_literal_search_preserves_pattern_characters_and_trims_outer_whitespace():
    request = ListProspectingRequest(search="  _100%  ")
    assert request.search == "_100%"
