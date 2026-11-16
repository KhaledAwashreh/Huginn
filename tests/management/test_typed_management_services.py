from datetime import UTC, datetime
from uuid import uuid4

from huginn.management.application.services.service_offerings import (
    ServiceOfferingService,
)
from huginn.management.domain.entities.service_offering import ServiceOffering
from huginn.management.domain.value_objects.common import (
    Page,
    Principal,
)


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


class Businesses:
    def __init__(self, owner_user_id, business_id):
        self.owner_user_id, self.business_id = owner_user_id, business_id

    def get_by_owner_user_id(self, owner_user_id):
        if owner_user_id != self.owner_user_id:
            return None
        return type("BusinessRef", (), {"id": self.business_id})()


def test_domain_service_accepts_commands_and_returns_entities_and_pages():
    now = datetime.now(UTC)
    user_id, business_id = uuid4(), uuid4()
    value = ServiceOffering(uuid4(), business_id, "Consulting", "Audit", now, now)
    uow, repo = UnitOfWork(), Offerings(value)
    service = ServiceOfferingService(
        lambda: uow,
        businesses_factory=lambda _: Businesses(user_id, business_id),
        offerings_factory=lambda _: repo,
    )
    principal = Principal(uuid4(), user_id)

    created = service.create(principal, name="Consulting", description="Audit")
    page = service.list(principal, limit=5, offset=2)

    assert created is value
    assert repo.created.business_id == business_id
    assert isinstance(page, Page)
    assert page.items == (value,)
    assert uow.commits == 1
