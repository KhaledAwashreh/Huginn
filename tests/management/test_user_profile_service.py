from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.domain import NotFoundError, Principal, ProfessionalProfile, User
from huginn.management.schemas import ProfessionalProfilePatch, UserPatch
from huginn.management.user_profile import UserProfileService


class FakeUnitOfWork:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0
        self.finished = False

    def __enter__(self):
        self.finished = False
        return self

    def __exit__(self, *_args):
        if not self.finished:
            self.rollback()
        return False

    def commit(self):
        self.commits += 1
        self.finished = True

    def rollback(self):
        self.rollbacks += 1
        self.finished = True


class FakeUsers:
    def __init__(self, record):
        self.record, self.calls = record, []

    def get_by_id(self, user_id):
        self.calls.append(("get", user_id))
        return self.record if user_id == self.record.id else None

    def update(self, user_id, changes):
        self.calls.append(("update", user_id, changes))
        return self.record if user_id == self.record.id else None


class FakeProfiles:
    def __init__(self, record):
        self.record, self.calls = record, []

    def get_owned(self, user_id):
        self.calls.append(("get", user_id))
        return self.record if user_id == self.record.user_id else None

    def update_owned(self, user_id, changes):
        self.calls.append(("update", user_id, changes))
        return self.record if user_id == self.record.user_id else None


def test_self_service_uses_principal_and_preserves_patch_field_presence():
    now, user_id = datetime.now(UTC), uuid4()
    users = FakeUsers(
        User(
            user_id,
            uuid4(),
            "Ada",
            "Lovelace",
            "ada@example.test",
            "+12025550123",
            "US",
            "UTC",
            now,
            now,
        )
    )
    profiles = FakeProfiles(
        ProfessionalProfile(uuid4(), user_id, None, None, (), (), (), now, now)
    )
    uow = FakeUnitOfWork()
    service = UserProfileService(
        lambda: uow,
        users_factory=lambda _uow: users,
        profiles_factory=lambda _uow: profiles,
    )
    principal = Principal(uuid4(), user_id)

    user_read = service.get_user(principal)
    profile_read = service.get_profile(principal)
    assert user_read["id"] == str(user_id)
    assert "account_id" not in user_read and "password_hash" not in user_read
    assert profile_read["skills"] == []

    service.update_user(principal, UserPatch.model_validate({"timezone": None}))
    service.update_profile(
        principal,
        ProfessionalProfilePatch.model_validate(
            {"headline": None, "skills": [{"name": "Python"}, {"name": "Python"}]}
        ),
    )
    assert users.calls[-1][1] == user_id
    assert users.calls[-1][2].values == {"timezone": None}
    assert users.calls[-1][2].supplied_fields == frozenset({"timezone"})
    assert profiles.calls[-1][1] == user_id
    assert profiles.calls[-1][2].values == {
        "headline": None,
        "skills": ({"name": "Python"}, {"name": "Python"}),
    }
    assert profiles.calls[-1][2].supplied_fields == frozenset({"headline", "skills"})
    assert (uow.commits, uow.rollbacks) == (2, 2)


@pytest.mark.parametrize("resource", ["user", "profile"])
def test_invalid_repository_return_rolls_back_without_commit(resource):
    now, user_id = datetime.now(UTC), uuid4()
    user = User(
        user_id,
        uuid4(),
        "Ada",
        "Lovelace",
        "invalid-email",
        "+12025550123",
        "US",
        None,
        now,
        now,
    )
    profile = ProfessionalProfile(
        uuid4(), user_id, None, None, ({"wrong": True},), (), (), now, now
    )
    users, profiles, uow = FakeUsers(user), FakeProfiles(profile), FakeUnitOfWork()
    service = UserProfileService(
        lambda: uow,
        users_factory=lambda _uow: users,
        profiles_factory=lambda _uow: profiles,
    )
    principal = Principal(uuid4(), user_id)

    with pytest.raises(ValueError):
        if resource == "user":
            service.update_user(
                principal, UserPatch.model_validate({"timezone": "UTC"})
            )
        else:
            service.update_profile(
                principal,
                ProfessionalProfilePatch.model_validate({"headline": "Updated"}),
            )
    assert (uow.commits, uow.rollbacks) == (0, 1)


def test_missing_user_is_indistinguishable_from_missing_profile_owner_record():
    now = datetime.now(UTC)
    users = FakeUsers(
        User(
            uuid4(),
            uuid4(),
            "Ada",
            "Lovelace",
            "ada@example.test",
            "+12025550123",
            "US",
            None,
            now,
            now,
        )
    )
    profiles = FakeProfiles(
        ProfessionalProfile(uuid4(), uuid4(), None, None, (), (), (), now, now)
    )
    uow = FakeUnitOfWork()
    service = UserProfileService(
        lambda: uow,
        users_factory=lambda _uow: users,
        profiles_factory=lambda _uow: profiles,
    )
    with pytest.raises(NotFoundError):
        service.get_user(Principal(uuid4(), uuid4()))
    with pytest.raises(NotFoundError):
        service.get_profile(Principal(uuid4(), uuid4()))
