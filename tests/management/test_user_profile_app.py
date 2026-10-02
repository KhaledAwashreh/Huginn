from datetime import UTC, datetime, timedelta
from uuid import uuid4

from huginn.management.domain import Principal, Session
from huginn.management.identity import SessionService
from tests.management.test_app_authentication import CSRF_TOKEN, SESSION_TOKEN, make_app


class TwoUserSessions:
    def __init__(self):
        self.records = {}
        for token, csrf in (("session-one", "csrf-one"), ("session-two", "csrf-two")):
            account_id, user_id = uuid4(), uuid4()
            session = Session(
                uuid4(),
                account_id,
                SessionService.digest(token),
                SessionService.digest(csrf),
                datetime.now(UTC),
                datetime.now(UTC) + timedelta(hours=1),
                None,
            )
            self.records[token] = (session, Principal(account_id, user_id), csrf)

    def get_by_token_digest(self, token_digest):
        for session, _principal, _csrf in self.records.values():
            if session.token_digest == token_digest:
                return session
        return None

    def get_active_principal_by_token_digest(self, token_digest, now):
        for session, principal, _csrf in self.records.values():
            if session.token_digest == token_digest and session.expires_at > now:
                return principal
        return None


class SelfServiceSpy:
    def __init__(self):
        self.calls = []

    def get_user(self, principal):
        self.calls.append(("get_user", principal.user_id))
        return {"id": str(principal.user_id)}

    def update_user(self, principal, patch):
        self.calls.append(("update_user", principal.user_id, patch))
        return {"id": str(principal.user_id)}

    def get_profile(self, principal):
        self.calls.append(("get_profile", principal.user_id))
        return {"user_id": str(principal.user_id)}

    def update_profile(self, principal, patch):
        self.calls.append(("update_profile", principal.user_id, patch))
        return {"user_id": str(principal.user_id)}


def test_two_users_patch_only_their_own_user_and_profile_and_owner_injection_fails():
    sessions = TwoUserSessions()
    service = SelfServiceSpy()
    app, _session_repo, _uow = make_app(sessions, user_profile_service=service)
    client = app.test_client()

    successful_calls = []
    for token, (_session, principal, csrf) in sessions.records.items():
        client.set_cookie("huginn_management_session", token)
        user_response = client.patch(
            "/api/v1/me",
            json={"first_name": f"First-{token}"},
            headers={"X-CSRF-Token": csrf},
        )
        profile_response = client.patch(
            "/api/v1/me/professional-profile",
            json={"headline": f"Headline-{token}"},
            headers={"X-CSRF-Token": csrf},
        )
        assert user_response.status_code == profile_response.status_code == 200
        assert user_response.json["id"] == str(principal.user_id)
        assert profile_response.json["user_id"] == str(principal.user_id)
        successful_calls.extend(service.calls[-2:])

    expected_users = [value[1].user_id for value in sessions.records.values()]
    assert [call[1] for call in successful_calls] == [
        expected_users[0],
        expected_users[0],
        expected_users[1],
        expected_users[1],
    ]
    assert successful_calls[0][2].first_name == "First-session-one"
    assert successful_calls[1][2].headline == "Headline-session-one"
    assert successful_calls[2][2].first_name == "First-session-two"
    assert successful_calls[3][2].headline == "Headline-session-two"
    assert expected_users[0] != expected_users[1]

    for token, (_session, _principal, csrf) in sessions.records.items():
        client.set_cookie("huginn_management_session", token)
        for path, payload in (
            ("/api/v1/me", {"first_name": "Injected", "user_id": str(uuid4())}),
            (
                "/api/v1/me/professional-profile",
                {"headline": "Injected", "user_id": str(uuid4())},
            ),
        ):
            response = client.patch(path, json=payload, headers={"X-CSRF-Token": csrf})
            assert response.status_code == 422

    assert service.calls == successful_calls


def test_invalid_nested_profile_patch_is_rejected_before_service_update():
    service = SelfServiceSpy()
    app, _sessions, _uow = make_app(user_profile_service=service)
    client = app.test_client()
    client.set_cookie("huginn_management_session", SESSION_TOKEN)
    response = client.patch(
        "/api/v1/me/professional-profile",
        json={
            "experience": [
                {
                    "organization": "Acme",
                    "role": "Engineer",
                    "end_month": "2020-01",
                    "is_current": True,
                }
            ]
        },
        headers={"X-CSRF-Token": CSRF_TOKEN},
    )
    assert response.status_code == 422
    assert service.calls == []
