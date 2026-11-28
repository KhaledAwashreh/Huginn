"""Business-owned configuration remains scoped to the requested acting User."""

from uuid import uuid4

import psycopg

from huginn.matchmaking.persistence.repositories.sql.configuration import (
    SqlConfigurationRepository,
)
from huginn.matchmaking_control.persistence.queries.target_user_query import (
    PostgresTargetUserQuery,
)
from tests.postgres_harness import provisioned_postgres


def test_configuration_and_control_resolve_each_users_sole_business():
    with (
        provisioned_postgres("huginn_business_configuration") as database_url,
        psycopg.connect(database_url) as connection,
    ):
        owners = []
        for label in ("first", "second"):
            account_id, user_id, business_id = uuid4(), uuid4(), uuid4()
            offering_id, icp_id, strategy_id = uuid4(), uuid4(), uuid4()
            connection.execute(
                "INSERT INTO operational.accounts(id,username,password_hash,status) "
                "VALUES (%s,%s,'test-hash','active')",
                (account_id, f"business-{label}-{account_id.hex}"),
            )
            connection.execute(
                "INSERT INTO operational.users(id,account_id,first_name,last_name,email,phone_number,country_of_residence) "
                "VALUES (%s,%s,%s,'Tester',%s,'000','US')",
                (user_id, account_id, label, f"{user_id.hex}@example.test"),
            )
            connection.execute(
                "INSERT INTO operational.businesses(id,owner_user_id) VALUES (%s,%s)",
                (business_id, user_id),
            )
            connection.execute(
                "INSERT INTO operational.service_offerings(id,business_id,name,description) VALUES (%s,%s,'Offering','Description')",
                (offering_id, business_id),
            )
            connection.execute(
                "INSERT INTO operational.ideal_client_profiles(id,business_id,name) VALUES (%s,%s,'ICP')",
                (icp_id, business_id),
            )
            connection.execute(
                "INSERT INTO operational.client_discovery_strategies(id,business_id,name,service_offering_id,ideal_client_profile_id,is_active) VALUES (%s,%s,'Strategy',%s,%s,true)",
                (strategy_id, business_id, offering_id, icp_id),
            )
            owners.append((user_id, strategy_id))

        repository = SqlConfigurationRepository(connection)
        for user_id, strategy_id in owners:
            configurations = repository.list_active_strategies(user_id)
            assert len(configurations) == 1
            assert configurations[0].strategy_id == strategy_id
            assert configurations[0].user_id == user_id
        targets = PostgresTargetUserQuery(connection)
        page = targets.search("", 0, 100)
        assert {item.id for item in page.items} == {owner[0] for owner in owners}
        assert all(item.has_active_strategies for item in page.items)
        assert targets.eligible_count() == 2

        names = targets.search("  FIRST Tester  ", 0, 10).items
        assert [item.id for item in names] == [owners[0][0]]
        assert (names[0].first_name, names[0].last_name) == ("first", "Tester")
        assert targets.search("business-first-", 0, 10).items == ()
        assert [item.id for item in targets.search(str(owners[1][0]), 0, 10).items] == [
            owners[1][0]
        ]
