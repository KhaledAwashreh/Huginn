class ActiveRunConflictError(Exception):
    def __init__(self, active_run_id: str) -> None:
        self.active_run_id = active_run_id
        super().__init__("an active matchmaking run already exists")


class RequestIdentityConflictError(Exception):
    pass


class TargetUserNotFoundError(Exception):
    pass


class TargetUserDisabledError(Exception):
    pass


class NoEligibleUsersError(Exception):
    pass


class TriggerRateLimitError(Exception):
    pass
