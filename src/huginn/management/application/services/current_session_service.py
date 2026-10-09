"""Session bootstrap use case from web-ui-foundation design section 2."""

from collections.abc import Callable
from datetime import UTC, datetime

from huginn.management.application.errors.errors import AuthenticationError
from huginn.management.application.requests.current_session_request import (
    CurrentSessionRequest,
)
from huginn.management.application.responses.current_session_response import (
    CurrentSessionResponse,
)
from huginn.management.persistence.contracts.repositories.session import (
    SessionRepository,
)
from huginn.management.persistence.contracts.unit_of_work import UnitOfWorkProtocol
from huginn.management.security.csrf import derive_csrf_token
from huginn.management.security.tokens import digest_token


class CurrentSessionService:
    def __init__(
        self,
        unit_of_work_factory: Callable[[], UnitOfWorkProtocol],
        *,
        sessions_factory: Callable[[UnitOfWorkProtocol], SessionRepository],
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._uow_factory = unit_of_work_factory
        self._sessions_factory = sessions_factory
        self._clock = clock or (lambda: datetime.now(UTC))

    def execute(self, request: CurrentSessionRequest) -> CurrentSessionResponse:
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("session clock must return a timezone-aware datetime")
        if not request.raw_token:
            raise AuthenticationError("authentication required")
        token_digest = digest_token(request.raw_token)
        proof = derive_csrf_token(request.raw_token)
        with self._uow_factory() as uow:
            repository = self._sessions_factory(uow)
            session = repository.get_by_token_digest(token_digest)
            if session is None or session.id != request.session_id:
                raise AuthenticationError("authentication required")
            session = repository.initialize_csrf_digest(
                request.session_id,
                token_digest,
                request.principal,
                session.csrf_digest,
                digest_token(proof),
                now.astimezone(UTC),
            )
            if session is None:
                raise AuthenticationError("authentication required")
            uow.commit()
            return CurrentSessionResponse(
                request.principal.account_id,
                request.principal.user_id,
                proof,
                session.expires_at,
                request.principal.role,
            )
