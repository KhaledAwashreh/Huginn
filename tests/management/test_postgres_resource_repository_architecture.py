from huginn.management.persistence.repositories.discovery_strategy import (
    PostgresClientDiscoveryStrategyRepository,
)
from huginn.management.persistence.repositories.ideal_client_profile import (
    PostgresIdealClientProfileRepository,
)
from huginn.management.persistence.repositories.service_offering import (
    PostgresServiceOfferingRepository,
)


def test_resource_postgres_implementations_live_in_resource_modules():
    assert PostgresServiceOfferingRepository.__module__.endswith(
        ".persistence.repositories.service_offering"
    )
    assert PostgresIdealClientProfileRepository.__module__.endswith(
        ".persistence.repositories.ideal_client_profile"
    )
    assert PostgresClientDiscoveryStrategyRepository.__module__.endswith(
        ".persistence.repositories.discovery_strategy"
    )
