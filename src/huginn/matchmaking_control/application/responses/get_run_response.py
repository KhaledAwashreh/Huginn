from dataclasses import dataclass

from huginn.matchmaking_control.application.read_models.run_detail import RunDetail


@dataclass(frozen=True)
class GetRunResponse:
    run: RunDetail | None
