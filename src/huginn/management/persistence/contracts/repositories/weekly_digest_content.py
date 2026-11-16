from typing import Protocol
from uuid import UUID

from huginn.management.domain.entities.weekly_digest_content import WeeklyDigestContent


class WeeklyDigestContentRepository(Protocol):
    def append(self, content: WeeklyDigestContent) -> WeeklyDigestContent: ...

    def get_by_id(
        self, business_id: UUID, delivery_id: UUID, content_id: UUID
    ) -> WeeklyDigestContent | None: ...

    def get_version(
        self, business_id: UUID, delivery_id: UUID, version: int
    ) -> WeeklyDigestContent | None: ...

    def get_current(
        self, business_id: UUID, delivery_id: UUID
    ) -> WeeklyDigestContent | None: ...

    def list_versions(
        self, business_id: UUID, delivery_id: UUID
    ) -> tuple[WeeklyDigestContent, ...]: ...
