from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

import psycopg
import pytest

from tests.postgres_harness import provisioned_postgres

_MIGRATION = Path("db/schema/operational-business-ownership.sql")
_LEGACY_FIXTURE = Path("tests/management/fixtures/business_ownership_prechange")
_MANAGEMENT_SETUP = Path("db/schema/operational-management-configuration.sql")
# The pinned SQL snapshots are exact historical source files from baseline
# 3c72b828b7f2d9b14dfa010fe7b84c95989c6a45; tests do not shell out to Git.


def _create_prechange_schema(connection):
    connection.execute(
        "CREATE SCHEMA gold; CREATE TABLE gold.company (id UUID PRIMARY KEY);"
    )
    for filename in (
        "operational.sql",
        "operational-recommendations.sql",
        "operational-weekly-digest.sql",
    ):
        connection.execute((_LEGACY_FIXTURE / filename).read_text())


def _assert_weekly_recipient_constraints(connection):
    constraints = dict(
        connection.execute(
            "SELECT conname,pg_get_constraintdef(oid) "
            "FROM pg_constraint "
            "WHERE conrelid='operational.weekly_digest_deliveries'::regclass "
            "AND conname IN ('weekly_digest_deliveries_recipient_user_fkey', "
            "'weekly_digest_deliveries_business_recipient_fkey', "
            "'weekly_digest_deliveries_batch_recipient_fkey')"
        ).fetchall()
    )
    assert set(constraints) == {
        "weekly_digest_deliveries_recipient_user_fkey",
        "weekly_digest_deliveries_business_recipient_fkey",
        "weekly_digest_deliveries_batch_recipient_fkey",
    }
    assert (
        "REFERENCES operational.users(id)"
        in constraints["weekly_digest_deliveries_recipient_user_fkey"]
    )
    assert (
        "REFERENCES operational.businesses(owner_user_id, id)"
        in constraints["weekly_digest_deliveries_business_recipient_fkey"]
    )
    assert (
        "REFERENCES operational.recommendation_batches(id, user_id)"
        in constraints["weekly_digest_deliveries_batch_recipient_fkey"]
    )


def test_ownership_setup_preserves_existing_config_personal_data_and_digest_state():
    user_a, user_b = uuid4(), uuid4()
    offering_a, offering_b = uuid4(), uuid4()
    profile_a, profile_b = uuid4(), uuid4()
    strategy_a, strategy_b = uuid4(), uuid4()
    delivery_id, batch_id = uuid4(), uuid4()
    updated_at = datetime(2026, 10, 1, 12, 30, tzinfo=UTC)

    with provisioned_postgres(  # noqa: SIM117 - nested connection depends on this URL
        "huginn_business_ownership_upgrade", apply_schema=False
    ) as database_url:
        with psycopg.connect(database_url) as connection:
            _create_prechange_schema(connection)

            account_a, account_b = (
                row[0]
                for row in connection.execute(
                    "INSERT INTO operational.accounts(username,password_hash) "
                    "VALUES (%s,'test-hash'),(%s,'test-hash') RETURNING id",
                    (f"legacy-{uuid4()}", f"legacy-{uuid4()}"),
                ).fetchall()
            )
            connection.execute(
                "INSERT INTO operational.users "
                "(id,account_id,first_name,last_name,email,phone_number,country_of_residence,timezone) "
                "VALUES (%s,%s,'Ada','Lovelace','a@example.test','+12025550001','US','UTC'),"
                "(%s,%s,'Grace','Hopper','b@example.test','+12025550002','US','UTC')",
                (user_a, account_a, user_b, account_b),
            )
            connection.execute(
                "INSERT INTO operational.professional_profiles(id,user_id,headline,skills) "
                "VALUES (%s,%s,'Personal profile','[{\"name\":\"Forecasting\"}]')",
                (uuid4(), user_a),
            )
            connection.execute(
                "INSERT INTO operational.service_offerings(id,user_id,name,description) "
                "VALUES (%s,%s,'A','Keep this'),(%s,%s,'B','Also keep this')",
                (offering_a, user_a, offering_b, user_b),
            )
            connection.execute(
                "INSERT INTO operational.ideal_client_profiles(id,user_id,name,industries) "
                "VALUES (%s,%s,'ICP A','[{\"name\":\"SaaS\"}]'),(%s,%s,'ICP B','[]')",
                (profile_a, user_a, profile_b, user_b),
            )
            connection.execute(
                "INSERT INTO operational.client_discovery_strategies "
                "(id,user_id,name,service_offering_id,ideal_client_profile_id,is_active) "
                "VALUES (%s,%s,'Strategy A',%s,%s,true),(%s,%s,'Strategy B',%s,%s,false)",
                (
                    strategy_a,
                    user_a,
                    offering_a,
                    profile_a,
                    strategy_b,
                    user_b,
                    offering_b,
                    profile_b,
                ),
            )
            connection.execute(
                "INSERT INTO operational.weekly_digest_subscriptions(user_id,enabled,updated_at) "
                "VALUES (%s,true,%s),(%s,false,%s)",
                (user_a, updated_at, user_b, updated_at),
            )
            connection.execute(
                "INSERT INTO operational.recommendation_batches "
                "(id,user_id,strategy_id,created_at,snapshot) VALUES (%s,%s,%s,%s,'{}')",
                (batch_id, user_a, strategy_a, updated_at),
            )
            connection.execute(
                "INSERT INTO operational.weekly_digest_deliveries "
                "(id,user_id,week_start,created_at,settled_at,state,batch_id,recipient,subject,body,company_ids) "
                "VALUES (%s,%s,'2026-10-05',%s,%s,'sent',%s,'verified@example.test',"
                "'Saved subject','Saved body','[\"9d66cb31-3713-411b-a5ec-2413338f14b8\"]')",
                (delivery_id, user_a, updated_at, updated_at, batch_id),
            )
            before = connection.execute(
                "SELECT p.id,p.headline,p.skills FROM operational.professional_profiles p WHERE user_id=%s",
                (user_a,),
            ).fetchone()
            accounts_before = connection.execute(
                "SELECT id,username,password_hash,status,created_at,updated_at "
                "FROM operational.accounts ORDER BY id"
            ).fetchall()
            users_before = connection.execute(
                "SELECT id,account_id,first_name,last_name,email,phone_number,"
                "country_of_residence,timezone,created_at,updated_at "
                "FROM operational.users ORDER BY id"
            ).fetchall()
            offerings_before = connection.execute(
                "SELECT id,name,description,created_at,updated_at "
                "FROM operational.service_offerings ORDER BY id"
            ).fetchall()
            profiles_before = connection.execute(
                "SELECT id,name,industries,company_sizes,geographies,exclusions,created_at,updated_at "
                "FROM operational.ideal_client_profiles ORDER BY id"
            ).fetchall()
            strategies_before = connection.execute(
                "SELECT id,name,service_offering_id,ideal_client_profile_id,is_active,created_at,updated_at "
                "FROM operational.client_discovery_strategies ORDER BY id"
            ).fetchall()
            deliveries_before = connection.execute(
                "SELECT id,user_id,week_start,created_at,settled_at,state,batch_id,recipient,subject,body,company_ids "
                "FROM operational.weekly_digest_deliveries"
            ).fetchall()
            subscriptions_before = connection.execute(
                "SELECT user_id,enabled,updated_at "
                "FROM operational.weekly_digest_subscriptions ORDER BY user_id"
            ).fetchall()
            batches_before = connection.execute(
                "SELECT id,user_id,strategy_id,created_at,snapshot "
                "FROM operational.recommendation_batches"
            ).fetchall()

            connection.execute(_MIGRATION.read_text())

            businesses = dict(
                connection.execute(
                    "SELECT owner_user_id,id FROM operational.businesses ORDER BY owner_user_id"
                ).fetchall()
            )
            business_a, business_b = businesses[user_a], businesses[user_b]
            connection.execute(
                "UPDATE operational.businesses SET name='Lovelace Studio',"
                "website='https://example.test',capabilities='[{\"name\":\"Forecasting\"}]' "
                "WHERE id=%s",
                (business_a,),
            )
            connection.execute(
                "UPDATE operational.business_recommendation_preferences "
                "SET repeat_interval_days=45 WHERE business_id=%s",
                (business_a,),
            )
            account_c = connection.execute(
                "INSERT INTO operational.accounts(username,password_hash) "
                "VALUES (%s,'test-hash') RETURNING id",
                (f"legacy-new-{uuid4()}",),
            ).fetchone()[0]
            user_c = connection.execute(
                "INSERT INTO operational.users "
                "(account_id,first_name,last_name,email,phone_number,country_of_residence,timezone) "
                "VALUES (%s,'Katherine','Johnson',%s,'+12025550003','US','UTC') RETURNING id",
                (account_c, f"c-{uuid4()}@example.test"),
            ).fetchone()[0]
            connection.execute(_MIGRATION.read_text())
            attached_c = connection.execute(
                "SELECT id FROM operational.businesses WHERE owner_user_id=%s",
                (user_c,),
            ).fetchone()[0]
            connection.execute(_MIGRATION.read_text())
            _assert_weekly_recipient_constraints(connection)
            with (
                pytest.raises(psycopg.errors.ForeignKeyViolation),
                connection.transaction(),
            ):
                connection.execute(
                    "INSERT INTO operational.weekly_digest_deliveries "
                    "(id,business_id,recipient_user_id,week_start,created_at) "
                    "VALUES (%s,%s,%s,'2026-10-12',%s)",
                    (uuid4(), business_a, uuid4(), updated_at),
                )
            with (
                pytest.raises(psycopg.errors.ForeignKeyViolation),
                connection.transaction(),
            ):
                connection.execute(
                    "INSERT INTO operational.weekly_digest_deliveries "
                    "(id,business_id,recipient_user_id,week_start,created_at) "
                    "VALUES (%s,%s,%s,'2026-10-12',%s)",
                    (uuid4(), business_a, user_b, updated_at),
                )
            assert connection.execute(
                "SELECT count(*) FROM operational.weekly_digest_deliveries"
            ).fetchone()[0] == len(deliveries_before)
            with (
                pytest.raises(psycopg.errors.ObjectNotInPrerequisiteState),
                connection.transaction(),
            ):
                connection.execute(
                    "UPDATE operational.recommendation_batches SET snapshot='{}' WHERE id=%s",
                    (batch_id,),
                )
            assert (
                connection.execute(
                    "SELECT id,user_id,strategy_id,created_at,snapshot "
                    "FROM operational.recommendation_batches"
                ).fetchall()
                == batches_before
            )
            empty_delivery_id = uuid4()
            connection.execute(
                "INSERT INTO operational.weekly_digest_deliveries "
                "(id,business_id,recipient_user_id,week_start,created_at) "
                "VALUES (%s,%s,%s,'2026-10-12',%s)",
                (empty_delivery_id, business_a, user_a, updated_at),
            )
            connection.execute(
                "UPDATE operational.weekly_digest_deliveries SET state='failed',settled_at=%s WHERE id=%s",
                (updated_at, empty_delivery_id),
            )
            assert connection.execute(
                "SELECT business_id,recipient_user_id,state,settled_at,batch_id,recipient,subject,body "
                "FROM operational.weekly_digest_deliveries WHERE id=%s",
                (empty_delivery_id,),
            ).fetchone() == (
                business_a,
                user_a,
                "failed",
                updated_at,
                None,
                None,
                None,
                None,
            )
            assert connection.execute(
                "SELECT owner_user_id,id,name,website,capabilities "
                "FROM operational.businesses ORDER BY owner_user_id"
            ).fetchall() == sorted(
                [
                    (
                        user_a,
                        business_a,
                        "Lovelace Studio",
                        "https://example.test",
                        [{"name": "Forecasting"}],
                    ),
                    (user_b, business_b, None, None, None),
                    (user_c, attached_c, None, None, None),
                ]
            )
            assert connection.execute(
                "SELECT b.owner_user_id,p.repeat_interval_days "
                "FROM operational.business_recommendation_preferences p "
                "JOIN operational.businesses b ON b.id=p.business_id "
                "ORDER BY b.owner_user_id"
            ).fetchall() == sorted([(user_a, 45), (user_b, 30), (user_c, 30)])
            account_ids = [row[0] for row in accounts_before]
            assert (
                connection.execute(
                    "SELECT id,username,password_hash,status,created_at,updated_at "
                    "FROM operational.accounts WHERE id=ANY(%s) ORDER BY id",
                    (account_ids,),
                ).fetchall()
                == accounts_before
            )
            user_ids = [row[0] for row in users_before]
            assert (
                connection.execute(
                    "SELECT id,account_id,first_name,last_name,email,phone_number,"
                    "country_of_residence,timezone,created_at,updated_at "
                    "FROM operational.users WHERE id=ANY(%s) ORDER BY id",
                    (user_ids,),
                ).fetchall()
                == users_before
            )
            assert connection.execute(
                "SELECT id,business_id,name,description,created_at,updated_at "
                "FROM operational.service_offerings ORDER BY id"
            ).fetchall() == sorted(
                [
                    (
                        row[0],
                        businesses[user_a if row[0] == offering_a else user_b],
                        *row[1:],
                    )
                    for row in offerings_before
                ]
            )
            assert connection.execute(
                "SELECT id,business_id,name,industries,company_sizes,geographies,"
                "exclusions,created_at,updated_at "
                "FROM operational.ideal_client_profiles ORDER BY id"
            ).fetchall() == sorted(
                [
                    (
                        row[0],
                        businesses[user_a if row[0] == profile_a else user_b],
                        *row[1:],
                    )
                    for row in profiles_before
                ]
            )
            assert connection.execute(
                "SELECT id,business_id,name,service_offering_id,ideal_client_profile_id,"
                "is_active,created_at,updated_at "
                "FROM operational.client_discovery_strategies ORDER BY id"
            ).fetchall() == sorted(
                [
                    (
                        row[0],
                        businesses[user_a if row[0] == strategy_a else user_b],
                        *row[1:],
                    )
                    for row in strategies_before
                ]
            )
            assert connection.execute(
                "SELECT id,business_id,recipient_user_id,week_start,created_at,settled_at,"
                "state,batch_id,recipient,subject,body,company_ids "
                "FROM operational.weekly_digest_deliveries WHERE id=ANY(%s) ORDER BY id",
                ([row[0] for row in deliveries_before],),
            ).fetchall() == [
                (
                    row[0],
                    businesses[row[1]],
                    row[1],
                    *row[2:],
                )
                for row in deliveries_before
            ]
            assert connection.execute(
                "SELECT b.owner_user_id,d.enabled,d.updated_at "
                "FROM operational.weekly_digest_subscriptions d "
                "JOIN operational.businesses b ON b.id=d.business_id "
                "ORDER BY b.owner_user_id"
            ).fetchall() == sorted(subscriptions_before)
            assert (
                connection.execute(
                    "SELECT id,user_id,strategy_id,created_at,snapshot "
                    "FROM operational.recommendation_batches"
                ).fetchall()
                == batches_before
            )
            assert connection.execute(
                "SELECT id,business_id,name,description FROM operational.service_offerings ORDER BY name"
            ).fetchall() == [
                (offering_a, business_a, "A", "Keep this"),
                (offering_b, business_b, "B", "Also keep this"),
            ]
            assert connection.execute(
                "SELECT id,business_id,name,industries FROM operational.ideal_client_profiles ORDER BY name"
            ).fetchall() == [
                (profile_a, business_a, "ICP A", [{"name": "SaaS"}]),
                (profile_b, business_b, "ICP B", []),
            ]
            assert connection.execute(
                "SELECT id,business_id,service_offering_id,ideal_client_profile_id,is_active "
                "FROM operational.client_discovery_strategies ORDER BY name"
            ).fetchall() == [
                (strategy_a, business_a, offering_a, profile_a, True),
                (strategy_b, business_b, offering_b, profile_b, False),
            ]
            assert connection.execute(
                "SELECT b.owner_user_id,d.enabled,d.updated_at "
                "FROM operational.weekly_digest_subscriptions d "
                "JOIN operational.businesses b ON b.id=d.business_id "
                "ORDER BY b.owner_user_id"
            ).fetchall() == sorted(
                [(user_a, True, updated_at), (user_b, False, updated_at)]
            )
            assert connection.execute(
                "SELECT id,business_id,recipient_user_id,state,batch_id,recipient,subject,body,company_ids "
                "FROM operational.weekly_digest_deliveries WHERE id=%s",
                (delivery_id,),
            ).fetchone() == (
                delivery_id,
                business_a,
                user_a,
                "sent",
                batch_id,
                "verified@example.test",
                "Saved subject",
                "Saved body",
                ["9d66cb31-3713-411b-a5ec-2413338f14b8"],
            )
            assert connection.execute(
                "SELECT b.owner_user_id,p.repeat_interval_days "
                "FROM operational.business_recommendation_preferences p "
                "JOIN operational.businesses b ON b.id=p.business_id "
                "ORDER BY b.owner_user_id"
            ).fetchall() == sorted([(user_a, 45), (user_b, 30), (user_c, 30)])
            assert (
                connection.execute(
                    "SELECT id,headline,skills FROM operational.professional_profiles WHERE user_id=%s",
                    (user_a,),
                ).fetchone()
                == before
            )
            assert (
                connection.execute(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE table_schema='operational' AND table_name IN "
                    "('service_offerings','ideal_client_profiles','client_discovery_strategies') "
                    "AND column_name='user_id'"
                ).fetchone()[0]
                == 0
            )


def test_empty_prechange_schema_can_run_ownership_setup_repeatedly():
    with (
        provisioned_postgres(
            "huginn_business_ownership_empty", apply_schema=False
        ) as database_url,
        psycopg.connect(database_url) as connection,
    ):
        _create_prechange_schema(connection)
        connection.execute(_MIGRATION.read_text())
        connection.execute(_MIGRATION.read_text())
        _assert_weekly_recipient_constraints(connection)
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.businesses"
            ).fetchone()[0]
            == 0
        )
        assert (
            connection.execute(
                "SELECT count(*) FROM operational.business_recommendation_preferences"
            ).fetchone()[0]
            == 0
        )


def test_management_configuration_setup_attaches_user_without_overwriting_values(
    management_database_url,
):
    with psycopg.connect(management_database_url) as connection:
        account_id = connection.execute(
            "INSERT INTO operational.accounts(username,password_hash) "
            "VALUES (%s,'test-hash') RETURNING id",
            (f"setup-{uuid4()}",),
        ).fetchone()[0]
        user_id = connection.execute(
            "INSERT INTO operational.users "
            "(account_id,first_name,last_name,email,phone_number,country_of_residence,timezone) "
            "VALUES (%s,'Ada','Lovelace',%s,'+12025550004','US','UTC') RETURNING id",
            (account_id, f"setup-{uuid4()}@example.test"),
        ).fetchone()[0]
        connection.execute(_MANAGEMENT_SETUP.read_text())
        business = connection.execute(
            "SELECT id,name,tagline,website,location,description,capabilities "
            "FROM operational.businesses WHERE owner_user_id=%s",
            (user_id,),
        ).fetchone()
        assert business is not None
        assert business[1:] == (None, None, None, None, None, None)
        business_id = business[0]
        assert connection.execute(
            "SELECT repeat_interval_days FROM operational.business_recommendation_preferences "
            "WHERE business_id=%s",
            (business_id,),
        ).fetchone() == (30,)
        connection.execute(
            "UPDATE operational.businesses SET name='Retained',website='https://example.test',"
            'capabilities=\'[{"name":"Forecasting"}]\' WHERE id=%s',
            (business_id,),
        )
        connection.execute(
            "UPDATE operational.business_recommendation_preferences "
            "SET repeat_interval_days=45 WHERE business_id=%s",
            (business_id,),
        )
        connection.execute(_MANAGEMENT_SETUP.read_text())
        assert connection.execute(
            "SELECT id,name,website,capabilities FROM operational.businesses "
            "WHERE owner_user_id=%s",
            (user_id,),
        ).fetchone() == (
            business_id,
            "Retained",
            "https://example.test",
            [{"name": "Forecasting"}],
        )
        assert connection.execute(
            "SELECT repeat_interval_days FROM operational.business_recommendation_preferences "
            "WHERE business_id=%s",
            (business_id,),
        ).fetchone() == (45,)


def test_ownership_setup_is_noop_on_fresh_schema(management_database_url):
    with psycopg.connect(management_database_url) as connection:
        connection.execute(
            Path("db/schema/operational-recommendations.sql").read_text()
        )
        connection.execute(Path("db/schema/operational-weekly-digest.sql").read_text())
        before = connection.execute(
            "SELECT id,owner_user_id,name,tagline,website,location,description,capabilities,created_at,updated_at "
            "FROM operational.businesses ORDER BY id"
        ).fetchall()
        preferences_before = connection.execute(
            "SELECT business_id,repeat_interval_days,updated_at "
            "FROM operational.business_recommendation_preferences ORDER BY business_id"
        ).fetchall()
        connection.execute(_MIGRATION.read_text())
        connection.execute(_MIGRATION.read_text())
        assert (
            connection.execute(
                "SELECT id,owner_user_id,name,tagline,website,location,description,capabilities,created_at,updated_at "
                "FROM operational.businesses ORDER BY id"
            ).fetchall()
            == before
        )
        assert (
            connection.execute(
                "SELECT business_id,repeat_interval_days,updated_at "
                "FROM operational.business_recommendation_preferences ORDER BY business_id"
            ).fetchall()
            == preferences_before
        )
