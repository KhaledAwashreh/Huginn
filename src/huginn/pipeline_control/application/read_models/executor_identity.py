from dataclasses import dataclass


@dataclass(frozen=True)
class ExecutorIdentity:
    host: str
    pid: int
    started_at: str
