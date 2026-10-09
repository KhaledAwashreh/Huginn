class ActiveInvocationConflictError(Exception):
    def __init__(self, active_invocation_id: str) -> None:
        super().__init__("a pipeline invocation is already active")
        self.active_invocation_id = active_invocation_id


class InvalidInvocationTransitionError(Exception):
    pass
