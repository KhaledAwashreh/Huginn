from dataclasses import dataclass
from uuid import UUID


@dataclass(frozen=True)
class ExecutionOwner:
    owner_id: UUID
    execution_id: UUID
    invocation_id: UUID | None
    host: str
    supervisor_pid: int
    supervisor_started_at: str
    resource_kind: str = "pipeline"
    matchmaking_run_id: UUID | None = None

    def __post_init__(self) -> None:
        if self.resource_kind not in {"pipeline", "matchmaking"}:
            raise ValueError("unsupported execution resource")
        if (
            self.resource_kind == "pipeline" and self.matchmaking_run_id is not None
        ) or (self.resource_kind == "matchmaking" and self.invocation_id is not None):
            raise ValueError("execution resource reference mismatch")
