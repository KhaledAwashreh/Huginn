from uuid import uuid4

import pytest

from huginn.management.discovery_strategies import ClientDiscoveryStrategyService
from huginn.management.domain import Principal
from huginn.management.ideal_client_profiles import IdealClientProfileService
from huginn.management.service_offerings import ServiceOfferingService

TOO_LARGE_OFFSET = 9_223_372_036_854_775_808


def fail_if_called():
    pytest.fail("a page beyond PostgreSQL's bigint range must not query storage")


@pytest.mark.parametrize(
    ("service_type", "list_kwargs"),
    [
        (ServiceOfferingService, {}),
        (IdealClientProfileService, {}),
        (ClientDiscoveryStrategyService, {"active": None}),
    ],
)
def test_list_services_return_empty_page_before_repository_query(
    service_type, list_kwargs
):
    service = service_type(
        fail_if_called,
        **{
            {
                ServiceOfferingService: "offerings_factory",
                IdealClientProfileService: "profiles_factory",
                ClientDiscoveryStrategyService: "strategies_factory",
            }[service_type]: lambda _uow: fail_if_called(),
        },
    )

    page = service.list(
        Principal(uuid4(), uuid4()),
        limit=50,
        offset=TOO_LARGE_OFFSET,
        **list_kwargs,
    )

    assert page == {
        "items": [],
        "offset": TOO_LARGE_OFFSET,
        "limit": 50,
        "has_more": False,
    }
