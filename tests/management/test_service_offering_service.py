from datetime import UTC, datetime
from uuid import uuid4

import pytest

from huginn.management.domain import NotFoundError, Page, Principal, ServiceOffering
from huginn.management.schemas import OfferingCreate, OfferingPatch
from huginn.management.service_offerings import ServiceOfferingService


class Uow:
    def __init__(self):
        self.commits = self.rollbacks = 0
        self.finished = False

    def __enter__(self):
        self.finished = False
        return self

    def __exit__(self, *_):
        if not self.finished:
            self.rollback()

    def commit(self):
        self.commits += 1
        self.finished = True

    def rollback(self):
        self.rollbacks += 1
        self.finished = True


class Repo:
    def __init__(self, record):
        self.record, self.calls = record, []

    def create(self, value):
        self.calls.append(("create", value))
        return self.record

    def get_owned(self, user_id, offering_id):
        self.calls.append(("get", user_id, offering_id))
        return (
            self.record
            if (user_id, offering_id) == (self.record.user_id, self.record.id)
            else None
        )

    def list_owned(self, user_id, *, limit, offset):
        self.calls.append(("list", user_id, limit, offset))
        return Page((self.record,), offset, limit, False)

    def update_owned(self, user_id, offering_id, changes):
        self.calls.append(("update", user_id, offering_id, changes))
        return (
            self.record
            if (user_id, offering_id) == (self.record.user_id, self.record.id)
            else None
        )

    def delete_owned(self, user_id, offering_id):
        self.calls.append(("delete", user_id, offering_id))
        return (user_id, offering_id) == (self.record.user_id, self.record.id)


def test_offering_service_derives_owner_commits_mutations_and_uses_paged_reads():
    user_id = uuid4()
    now = datetime.now(UTC)
    record = ServiceOffering(uuid4(), user_id, "Consulting", "Audit", now, now)
    uow, repo = Uow(), Repo(record)
    service = ServiceOfferingService(lambda: uow, offerings_factory=lambda _: repo)
    principal = Principal(uuid4(), user_id)
    created = service.create(
        principal, OfferingCreate(name="Consulting", description="Audit")
    )
    assert created["id"] == str(record.id) and repo.calls[-1][1].user_id == user_id
    assert service.get(principal, record.id)["user_id"] == str(user_id)
    page = service.list(principal, limit=3, offset=4)
    assert page["offset"] == 4 and page["items"][0]["name"] == "Consulting"
    service.update(principal, record.id, OfferingPatch(description="Review"))
    assert repo.calls[-1][-1].values == {"description": "Review"}
    service.delete(principal, record.id)
    assert uow.commits == 3


def test_offering_service_hides_cross_owner_and_missing_as_not_found():
    now = datetime.now(UTC)
    record = ServiceOffering(uuid4(), uuid4(), "Name", "Description", now, now)
    service = ServiceOfferingService(
        lambda: Uow(), offerings_factory=lambda _: Repo(record)
    )
    with pytest.raises(NotFoundError):
        service.get(Principal(uuid4(), uuid4()), record.id)


@pytest.mark.parametrize("operation", ["create", "update"])
def test_invalid_repository_return_rolls_back_before_commit(operation):
    user_id = uuid4()
    now = datetime.now(UTC)
    invalid = ServiceOffering(uuid4(), user_id, " ", "Audit", now, now)
    uow = Uow()
    service = ServiceOfferingService(
        lambda: uow, offerings_factory=lambda _: Repo(invalid)
    )
    principal = Principal(uuid4(), user_id)

    with pytest.raises(ValueError):
        if operation == "create":
            service.create(
                principal, OfferingCreate(name="Consulting", description="Audit")
            )
        else:
            service.update(principal, invalid.id, OfferingPatch(name="Consulting"))

    assert uow.commits == 0
    assert uow.rollbacks == 1
