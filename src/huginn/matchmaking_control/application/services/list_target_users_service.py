from collections.abc import Callable

from huginn.matchmaking_control.application.requests.list_target_users_request import (
    ListTargetUsersRequest,
)
from huginn.matchmaking_control.application.responses.list_target_users_response import (
    ListTargetUsersResponse,
)
from huginn.matchmaking_control.persistence.contracts.unit_of_work import (
    MatchmakingControlUnitOfWork,
)


class ListTargetUsersService:
    def __init__(
        self, unit_of_work_factory: Callable[[], MatchmakingControlUnitOfWork]
    ) -> None:
        self._uow_factory = unit_of_work_factory

    def execute(self, request: ListTargetUsersRequest) -> ListTargetUsersResponse:
        _validate_page(request.offset, request.limit)
        if len(request.search) > 200:
            raise ValueError("search must be at most 200 characters")
        with self._uow_factory() as uow:
            page = uow.target_users.search(
                request.search.strip(), request.offset, request.limit
            )
            total = uow.target_users.eligible_count()
        return ListTargetUsersResponse(page=page, total_eligible_count=total)


def _validate_page(offset: int, limit: int) -> None:
    if offset < 0 or not 1 <= limit <= 100:
        raise ValueError("page limit must be 1..100 and offset nonnegative")
