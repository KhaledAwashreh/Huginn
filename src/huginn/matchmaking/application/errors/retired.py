"""Stable failure raised by retired Match creation entry points."""


class MatchmakingRetiredError(RuntimeError):
    code = "matchmaking_retired"

    def __init__(self) -> None:
        super().__init__("Match creation has been retired")
