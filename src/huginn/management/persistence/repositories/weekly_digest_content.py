"""PostgreSQL adapter for immutable weekly content and ordered members."""

from typing import Any
from uuid import UUID

from huginn.management.domain.entities.weekly_digest_content import WeeklyDigestContent
from huginn.management.domain.errors.errors import (
    ConflictError,
    ValidationDomainError,
)
from huginn.management.domain.value_objects.weekly_digest_member import (
    WeeklyDigestMember,
)
from huginn.management.persistence.contracts.database import DatabaseSession
from huginn.management.persistence.contracts.repositories.weekly_digest_content import (
    WeeklyDigestContentRepository,
)
from huginn.management.persistence.errors.database import IntegrityError

_CONTENT_COLUMNS = (
    "id,delivery_id,business_id,recipient_user_id,version,created_at,"
    "subscription_updated_at,recipient,subject,body,message_id"
)
_MEMBER_COLUMNS = (
    "company_id,recommendation_id,assessment_revision_id,offer_cycle_id,position"
)


class PostgresWeeklyDigestContentRepository(WeeklyDigestContentRepository):
    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    def append(self, content: WeeklyDigestContent) -> WeeklyDigestContent:
        if not isinstance(content, WeeklyDigestContent):
            raise ValidationDomainError("Weekly content must use its immutable model")
        try:
            self.connection.execute(
                f"INSERT INTO operational.weekly_digest_contents ({_CONTENT_COLUMNS}) "
                "VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    content.id,
                    content.delivery_id,
                    content.business_id,
                    content.recipient_user_id,
                    content.version,
                    content.created_at,
                    content.subscription_updated_at,
                    content.recipient,
                    content.subject,
                    content.body,
                    content.message_id,
                ),
            )
            for member in content.members:
                self.connection.execute(
                    f"INSERT INTO operational.weekly_digest_members "
                    f"(content_id,delivery_id,business_id,{_MEMBER_COLUMNS}) "
                    "VALUES (%s,%s,%s,%s,%s,%s,%s,%s)",
                    (
                        content.id,
                        content.delivery_id,
                        content.business_id,
                        member.company_id,
                        member.recommendation_id,
                        member.assessment_revision_id,
                        member.offer_cycle_id,
                        member.position,
                    ),
                )
        except IntegrityError as exc:
            if exc.sqlstate in {"23503", "23505", "23514"}:
                raise ConflictError(
                    "Weekly content identity or member scope conflicts with persisted history"
                ) from exc
            raise ValidationDomainError(
                "Weekly content violates persistence rules"
            ) from exc
        return content

    def get_by_id(
        self, business_id: UUID, delivery_id: UUID, content_id: UUID
    ) -> WeeklyDigestContent | None:
        _ids(business_id, delivery_id, content_id)
        row = self.connection.execute(
            f"SELECT {_CONTENT_COLUMNS} FROM operational.weekly_digest_contents "
            "WHERE business_id=%s AND delivery_id=%s AND id=%s",
            (business_id, delivery_id, content_id),
        ).fetchone()
        return self._map(row) if row is not None else None

    def get_version(
        self, business_id: UUID, delivery_id: UUID, version: int
    ) -> WeeklyDigestContent | None:
        _ids(business_id, delivery_id)
        if type(version) is not int or version < 1:
            raise ValidationDomainError("Weekly content version must be positive")
        row = self.connection.execute(
            f"SELECT {_CONTENT_COLUMNS} FROM operational.weekly_digest_contents "
            "WHERE business_id=%s AND delivery_id=%s AND version=%s",
            (business_id, delivery_id, version),
        ).fetchone()
        return self._map(row) if row is not None else None

    def get_current(
        self, business_id: UUID, delivery_id: UUID
    ) -> WeeklyDigestContent | None:
        _ids(business_id, delivery_id)
        row = self.connection.execute(
            "SELECT current_content_id FROM operational.weekly_digest_deliveries "
            "WHERE business_id=%s AND id=%s",
            (business_id, delivery_id),
        ).fetchone()
        if row is None or row[0] is None:
            return None
        return self.get_by_id(business_id, delivery_id, row[0])

    def list_versions(
        self, business_id: UUID, delivery_id: UUID
    ) -> tuple[WeeklyDigestContent, ...]:
        _ids(business_id, delivery_id)
        rows = self.connection.execute(
            f"SELECT {_CONTENT_COLUMNS} FROM operational.weekly_digest_contents "
            "WHERE business_id=%s AND delivery_id=%s ORDER BY version",
            (business_id, delivery_id),
        ).fetchall()
        return tuple(self._map(row) for row in rows)

    def _map(self, row: tuple[Any, ...]) -> WeeklyDigestContent:
        member_rows = self.connection.execute(
            f"SELECT {_MEMBER_COLUMNS} FROM operational.weekly_digest_members "
            "WHERE content_id=%s AND delivery_id=%s AND business_id=%s "
            "ORDER BY position",
            (row[0], row[1], row[2]),
        ).fetchall()
        members = tuple(WeeklyDigestMember(*member) for member in member_rows)
        return WeeklyDigestContent(
            id=row[0],
            delivery_id=row[1],
            business_id=row[2],
            recipient_user_id=row[3],
            version=row[4],
            created_at=row[5],
            subscription_updated_at=row[6],
            recipient=row[7],
            subject=row[8],
            body=row[9],
            message_id=row[10],
            members=members,
        )


def _ids(*values: UUID) -> None:
    if any(not isinstance(value, UUID) for value in values):
        raise ValidationDomainError("Weekly content IDs must be UUIDs")
