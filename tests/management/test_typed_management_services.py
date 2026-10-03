from datetime import UTC, datetime
from uuid import uuid4

from huginn.management.domain.common import (
    Page,
    Principal,
)
from huginn.management.domain.service_offering import (
    NewServiceOffering,
    ServiceOffering,
)
from huginn.management.services.service_offerings import ServiceOfferingService


class UnitOfWork:
    def __init__(self):
        self.commits = 0
        self.finished = False

    def __enter__(self):
        self.finished = False
        return self

    def __exit__(self, *_):
        return False

    def commit(self):
        self.commits += 1
        self.finished = True


class Offerings:
    def __init__(self, value):
        self.value = value
        self.created = None

    def create(self, value):
        self.created = value
        return self.value

    def list_owned(self, user_id, *, limit, offset):
        return Page((self.value,), offset, limit, False)


def test_domain_service_accepts_commands_and_returns_entities_and_pages():
    now = datetime.now(UTC)
    user_id = uuid4()
    value = ServiceOffering(uuid4(), user_id, "Consulting", "Audit", now, now)
    uow, repo = UnitOfWork(), Offerings(value)
    service = ServiceOfferingService(lambda: uow, offerings_factory=lambda _: repo)
    principal = Principal(uuid4(), user_id)

    created = service.create(
        principal,
        NewServiceOffering(uuid4(), "Consulting", "Audit"),
    )
    page = service.list(principal, limit=5, offset=2)

    assert created is value
    assert repo.created.user_id == user_id
    assert isinstance(page, Page)
    assert page.items == (value,)
    assert uow.commits == 1
