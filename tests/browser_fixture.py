"""Disposable real-API browser fixture; never uses a configured/shared database."""

import os
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import psycopg
import uvicorn
from psycopg.types.json import Jsonb

from huginn.management.app import create_account_administration_services, create_app
from huginn.management.application.commands.provisioning import ProvisionIdentity
from huginn.management.config import ManagementConfig
from huginn.management.security.tokens import digest_token
from huginn.pipeline_control.domain.value_objects.stage_plan import SUPPORTED_STAGE_PLAN
from tests.browser_lifecycle_mail import browser_lifecycle_mail
from tests.postgres_harness import provisioned_postgres

PASSWORD = "browser-only-correct-horse-battery"
LEGACY_TOKEN = "legacy-browser-only-" + "a" * 64
LEGACY_PROOF = "legacy-browser-proof-" + "b" * 64


def _seed_admin_history(connection, account_id: UUID) -> None:
    """Harmless saved projections: no source or matcher is invoked."""
    now = datetime.now(UTC)
    for index, state in enumerate(("succeeded", "failed", "interrupted")):
        invocation_id = UUID(int=9001 + index)
        requested = now - timedelta(hours=index + 1)
        connection.execute(
            "INSERT INTO ops.pipeline_invocations "
            "(id,requester_account_id,request_id,state,requested_at,started_at,finished_at,plan,company_results_tracking_state) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,'tracked')",
            (
                invocation_id,
                account_id,
                uuid4(),
                state,
                requested,
                requested,
                requested + timedelta(minutes=2),
                Jsonb(SUPPORTED_STAGE_PLAN.to_json()),
            ),
        )
        job_ids = {}
        for stage in SUPPORTED_STAGE_PLAN.stages:
            if state == "interrupted" and stage.order > 1:
                continue
            stage_state = (
                "succeeded"
                if state == "succeeded"
                else ("failed" if stage.order == 0 else "skipped")
            )
            if state == "interrupted":
                stage_state = "running"
            job_id = uuid4()
            job_ids[stage.name] = job_id
            connection.execute(
                "INSERT INTO ops.job_runs (id,source,started_at,finished_at,status,rows_written,invocation_id,execution_kind) VALUES (%s,%s,%s,%s,%s,%s,%s,'stage')",
                (
                    job_id,
                    stage.name,
                    requested,
                    None
                    if stage_state == "running"
                    else requested + timedelta(seconds=10),
                    stage_state,
                    105 if stage.name == "gold.company" else 0,
                    invocation_id,
                ),
            )
            for source in stage.source_children:
                connection.execute(
                    "INSERT INTO ops.job_runs (source,started_at,finished_at,status,rows_written,invocation_id,parent_job_run_id,execution_kind) VALUES (%s,%s,%s,%s,0,%s,%s,'source')",
                    (
                        source,
                        requested,
                        None
                        if stage_state == "running"
                        else requested + timedelta(seconds=5),
                        stage_state,
                        invocation_id,
                        job_id,
                    ),
                )
        for sequence in range(1, 106):
            connection.execute(
                "INSERT INTO ops.pipeline_invocation_events (invocation_id,sequence,occurred_at,kind,transition_key,safe_message) VALUES (%s,%s,%s,'fixture',%s,%s)",
                (
                    invocation_id,
                    sequence,
                    requested + timedelta(seconds=sequence),
                    f"fixture:{sequence}",
                    f"Saved harmless event {sequence}: <script>safe text only</script>",
                ),
            )
        if state == "succeeded":
            for company_index in range(105):
                company_id = connection.execute(
                    "INSERT INTO gold.company(domain,name,country,business_sector,company_scale) VALUES (%s,%s,'USA',ARRAY['B2B'],'11-100') RETURNING id",
                    (
                        f"admin-fixture-{company_index}.example.test",
                        f"Saved company {company_index:03d}",
                    ),
                ).fetchone()[0]
                connection.execute(
                    "INSERT INTO ops.pipeline_company_results(invocation_id,company_id,stage_job_run_id) VALUES (%s,%s,%s)",
                    (invocation_id, company_id, job_ids["gold.company"]),
                )


def _seed_matching_history(connection, account_id: UUID) -> None:
    """Bounded real projections and searchable identities, without evaluation."""
    now = datetime.now(UTC) - timedelta(minutes=5)
    user_ids = []
    for index in range(105):
        user_account = connection.execute(
            "INSERT INTO operational.accounts(username,password_hash) VALUES (%s,'fixture-not-a-login-hash') RETURNING id",
            (f"target-{index:03d}",),
        ).fetchone()[0]
        user_id = connection.execute(
            "INSERT INTO operational.users(account_id,first_name,last_name,email,phone_number,country_of_residence,timezone) VALUES (%s,'Saved','Target',%s,'+12025550123','US','UTC') RETURNING id",
            (user_account, f"target-{index}@example.test"),
        ).fetchone()[0]
        user_ids.append(user_id)
        offering_id = connection.execute(
            "INSERT INTO operational.service_offerings(user_id,name,description) VALUES (%s,'Saved offering','Fixture only') RETURNING id",
            (user_id,),
        ).fetchone()[0]
        icp_id = connection.execute(
            "INSERT INTO operational.ideal_client_profiles(user_id,name) VALUES (%s,'Saved profile') RETURNING id",
            (user_id,),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO operational.client_discovery_strategies(user_id,name,service_offering_id,ideal_client_profile_id,is_active) VALUES (%s,'Saved strategy',%s,%s,true)",
            (user_id, offering_id, icp_id),
        )
    for index, state in enumerate(("completed_with_errors", "interrupted")):
        run_id = UUID(int=9101 + index)
        connection.execute(
            "INSERT INTO ops.matchmaking_runs(id,requester_account_id,request_id,canonical_request,target_kind,cutoff,as_of,state,requested_at,started_at,finished_at,target_count,settled_target_count) VALUES (%s,%s,%s,'{}','all_eligible',%s,%s,%s,%s,%s,%s,105,105)",
            (
                run_id,
                account_id,
                uuid4(),
                now - timedelta(days=30),
                now,
                state,
                now,
                now,
                now,
            ),
        )
        for ordinal, user_id in enumerate(user_ids):
            outcome = (
                "succeeded"
                if ordinal < 103
                else ("failed" if ordinal == 103 else "commit_outcome_unknown")
            )
            if state == "interrupted":
                outcome = "not_executed" if ordinal < 103 else "commit_outcome_unknown"
            success = outcome == "succeeded"
            connection.execute(
                "INSERT INTO ops.matchmaking_run_users(run_id,user_id,ordinal,state,started_at,finished_at,strategies_evaluated,strategies_skipped,unique_candidates_count,created_matches_count,existing_matches_skipped_count,safe_reason) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    run_id,
                    user_id,
                    ordinal,
                    outcome,
                    now,
                    now,
                    1 if success else None,
                    1 if success else None,
                    2 if success else None,
                    1 if success else None,
                    1 if success else None,
                    None
                    if success
                    else (
                        "database_failure"
                        if outcome == "failed"
                        else (
                            "commit_outcome_unknown"
                            if outcome == "commit_outcome_unknown"
                            else None
                        )
                    ),
                ),
            )
            if ordinal == 0 and success:
                for _ in range(55):
                    connection.execute(
                        "INSERT INTO ops.matchmaking_run_skipped_strategies(run_id,user_id,strategy_id,reason) VALUES (%s,%s,%s,'incomplete_icp')",
                        (run_id, user_id, uuid4()),
                    )


def _seed_owner_matches(connection, user_id: UUID) -> None:
    """Disposable owner pages with current Gold context, without matching."""
    now = datetime.now(UTC)
    for index in range(105):
        company_id = connection.execute(
            "INSERT INTO gold.company(domain,name,country,business_sector,company_scale) "
            "VALUES (%s,%s,'USA',ARRAY['B2B'],'11-100') RETURNING id",
            (f"owner-match-{index}.example.test", f"Current match company {index:03d}"),
        ).fetchone()[0]
        connection.execute(
            "INSERT INTO operational.match(id,user_id,company_id,status,notes,created_at,updated_at) "
            "VALUES (%s,%s,%s,%s,%s,%s,%s)",
            (
                UUID(int=9800 + index),
                user_id,
                company_id,
                "contacted" if index == 1 else "new",
                "Stored notes <script>plain text</script>",
                now - timedelta(minutes=index),
                now,
            ),
        )
        if index == 0:
            for signal_index in range(105):
                connection.execute(
                    "INSERT INTO gold.company_signal(company_id,signal_type,source,source_stable_id,source_url,"
                    "description,stage,occurred_at,ingested_at) VALUES (%s,'hiring','hn',%s,%s,%s,'seed',%s,%s)",
                    (
                        company_id,
                        f"owner-browser-{signal_index}",
                        "javascript:alert(1)"
                        if signal_index == 0
                        else "https://example.test/signal",
                        f"Current signal {signal_index:03d}",
                        now - timedelta(minutes=signal_index),
                        now,
                    ),
                )


def main() -> None:
    name = f"huginn_browser_{uuid4().hex}"
    with provisioned_postgres(name) as database_url:
        config = ManagementConfig(database_url, environment="test")
        provisioning = create_account_administration_services(config).provisioning
        identities = {}
        for username in (
            "browser-ada",
            "browser-bob",
            "browser-legacy",
            "browser-config",
            "browser-password",
            "browser-visual",
            "browser-admin",
            "browser-matches",
        ):
            identities[username] = provisioning.provision(
                ProvisionIdentity(
                    username=username,
                    first_name="Ada" if username == "browser-ada" else "Bob",
                    last_name="Browser",
                    email=f"{username}@example.test",
                    phone_number="+12025550123",
                    country_of_residence="US",
                    timezone="UTC",
                    password=PASSWORD,
                )
            )
        with psycopg.connect(database_url) as connection:
            connection.execute(
                "UPDATE operational.accounts SET role = 'admin' WHERE id = %s",
                (identities["browser-admin"].account_id,),
            )
            _seed_admin_history(connection, identities["browser-admin"].account_id)
            _seed_matching_history(connection, identities["browser-admin"].account_id)
            _seed_owner_matches(connection, identities["browser-matches"].user_id)
            for label, country, sectors, size in (
                ("Collected Health", "USA", ["Healthcare", "B2B"], "11-100"),
                ("Collected Finance", "United States", ["Fintech"], "0-10"),
                ("Collected Canadian", "Canada", ["B2B"], "101-1000"),
            ):
                connection.execute(
                    "INSERT INTO gold.company(domain,name,country,business_sector,company_scale) VALUES(%s,%s,%s,%s,%s)",
                    (
                        f"{label.lower().replace(' ', '-')}.example.test",
                        label,
                        country,
                        sectors,
                        size,
                    ),
                )
            connection.execute(
                "INSERT INTO operational.sessions "
                "(account_id, token_digest, csrf_digest, expires_at) VALUES (%s,%s,%s,%s)",
                (
                    identities["browser-legacy"].account_id,
                    digest_token(LEGACY_TOKEN),
                    digest_token(LEGACY_PROOF),
                    datetime.now(UTC) + timedelta(hours=1),
                ),
            )
        with browser_lifecycle_mail(config) as lifecycle_config:
            uvicorn.run(
                create_app(lifecycle_config),
                host="127.0.0.1",
                port=int(os.environ.get("HUGINN_BROWSER_API_PORT", "8000")),
                log_level="warning",
            )


if __name__ == "__main__":
    main()
