"""Owner-controlled Account lifecycle use cases."""

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any

from huginn.management.errors.domain import (
    NotFoundError,
    ValidationDomainError,
)
from huginn.management.repositories.protocols.account import AccountRepository
from huginn.management.repositories.protocols.session import SessionRepository
from huginn.management.security.passwords import Password, hash_password


class AccountAdminService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], Any],
        *,
        accounts_factory: Callable[[Any], AccountRepository],
        sessions_factory: Callable[[Any], SessionRepository],
        clock: Callable[[], datetime] | None = None,
        hash_password_fn: Callable[[Password], str] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._accounts_factory = accounts_factory
        self._sessions_factory = sessions_factory
        self._clock = clock or (lambda: datetime.now(UTC))
        self._hash_password = hash_password_fn or hash_password

    def set_status(self, username: str, status: str) -> None:
        if status not in {"active", "disabled"}:
            raise ValidationDomainError("invalid account status")
        with self._uow_factory() as uow:
            accounts = self._accounts_factory(uow)
            account = accounts.get_by_normalized_username(username)
            if account is None:
                raise NotFoundError("account not found")
            if accounts.set_status(account.id, status) is None:
                raise NotFoundError("account not found")
            if status == "disabled":
                self._sessions_factory(uow).revoke_for_account(account.id, self._now())
            uow.commit()

    def reset_password(self, username: str, password: str) -> None:
        try:
            secret = Password(password)
        except (TypeError, ValueError) as exc:
            raise ValidationDomainError("invalid identity field: password") from exc
        with self._uow_factory() as uow:
            accounts = self._accounts_factory(uow)
            account = accounts.get_by_normalized_username(username)
            if account is None:
                raise NotFoundError("account not found")
            if (
                accounts.set_password_hash(account.id, self._hash_password(secret))
                is None
            ):
                raise NotFoundError("account not found")
            self._sessions_factory(uow).revoke_for_account(account.id, self._now())
            uow.commit()

    def _now(self) -> datetime:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("account administration clock must be timezone-aware")
        return now.astimezone(UTC)
