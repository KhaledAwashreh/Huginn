from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.domain.common import Principal
from huginn.management.domain.professional_profile import (
    ProfessionalProfile,
    ProfessionalProfileChanges,
)
from huginn.management.domain.user import (
    User,
    UserChanges,
)
from huginn.management.errors.domain import NotFoundError
from huginn.management.services.user_profile import UserProfileService


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

    def create(self, profile):
        self.record = profile
        return profile

    def get_owned(self, user_id):
        self.calls.append(("get", user_id))
        return self.record if user_id == self.record.user_id else None

    def update(self, user_id, changes):
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
    assert not hasattr(profiles, "update_owned")
    uow = FakeUnitOfWork()
    service = UserProfileService(
        lambda: uow,
        users_factory=lambda _uow: users,
        profiles_factory=lambda _uow: profiles,
    )
    principal = Principal(uuid4(), user_id)

    user_read = service.get_user(principal)
    profile_read = service.get_profile(principal)
    assert user_read.id == user_id
    assert profile_read.skills == ()

    service.update_user(
        principal, UserChanges({"timezone": None}, frozenset({"timezone"}))
    )
    service.update_profile(
        principal,
        ProfessionalProfileChanges(
            {"headline": None, "skills": ({"name": "Python"}, {"name": "Python"})},
            frozenset({"headline", "skills"}),
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
