from uuid import uuid4

from cryptography.fernet import Fernet
from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig
from huginn.management.presentation.cli.weekly_digest import main
from huginn.management.security.digest_unsubscribe import digest_unsubscribe_token


class Subscriptions:
    def __init__(self):
        self.disabled = []
        self.enabled = []

    def subscribe(self, user):
        self.enabled.append(user)

    def unsubscribe(self, user):
        self.disabled.append(user)


def test_cli_subscribe_and_dry_run_use_explicit_injected_services(capsys):
    subscriptions = Subscriptions()
    user = uuid4()
    assert (
        main(
            ["subscribe", "--user-id", str(user)],
            config_factory=lambda: None,
            subscriptions_factory=lambda _: subscriptions,
        )
        == 0
    )
    assert subscriptions.enabled == [user]
    assert '"subscribed"' in capsys.readouterr().out

    class Digest:
        def run(self, **args):
            assert args == {"limit": 3, "daily_limit": 100, "dry_run": True}
            return {"eligible": 1, "sent": 0}

    assert (
        main(
            ["send", "--dry-run", "--limit", "3"],
            config_factory=lambda: None,
            digest_factory=lambda _: Digest(),
        )
        == 0
    )


def test_signed_unsubscribe_get_never_mutates_and_post_only_disables_bound_user():
    subscriptions = Subscriptions()
    key = Fernet.generate_key().decode()
    user = uuid4()
    app = create_app(
        ManagementConfig("unused", environment="test", lifecycle_proof_key=key),
        digest_subscriptions_service=subscriptions,
    )
    with TestClient(app) as client:
        query = {"user_id": str(user), "token": digest_unsubscribe_token(key, user)}
        response = client.get("/weekly-digest/unsubscribe")
        assert response.status_code == 200
        assert '<form method="post"' in response.text
        assert response.headers["cache-control"] == "no-store"
        assert "location.hash" in response.text
        assert (
            '<form method="post" action="/weekly-digest/unsubscribe"' in response.text
        )
        assert query["token"] not in response.text
        assert subscriptions.disabled == []
        assert client.post("/weekly-digest/unsubscribe", data=query).status_code == 200
        assert subscriptions.disabled == [user]
        for token in ("bad", "é" * 64, digest_unsubscribe_token(key, uuid4())):
            assert (
                client.post(
                    "/weekly-digest/unsubscribe", data={**query, "token": token}
                ).status_code
                == 404
            )
        assert subscriptions.disabled == [user]


def test_unsubscribe_query_tokens_are_not_accepted_as_post_authorization():
    subscriptions = Subscriptions()
    key = Fernet.generate_key().decode()
    user = uuid4()
    app = create_app(
        ManagementConfig("unused", environment="test", lifecycle_proof_key=key),
        digest_subscriptions_service=subscriptions,
    )
    with TestClient(app) as client:
        query = {"user_id": str(user), "token": digest_unsubscribe_token(key, user)}
        assert (
            client.post("/weekly-digest/unsubscribe", params=query).status_code == 404
        )
        assert (
            client.post(
                "/weekly-digest/unsubscribe",
                content="x" * 2049,
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            ).status_code
            == 404
        )
        assert subscriptions.disabled == []
