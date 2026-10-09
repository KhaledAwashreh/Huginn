from datetime import datetime
from typing import Protocol
from uuid import UUID

from huginn.pipeline_control.domain.entities.pipeline_invocation import (
    PipelineInvocation,
)


class InvocationRepository(Protocol):
    def lock_trigger_admission(self) -> None: ...
    def get_by_request(
        self, requester_account_id: UUID, request_id: UUID
    ) -> PipelineInvocation | None: ...
    def get(self, invocation_id: UUID) -> PipelineInvocation | None: ...
    def active(self) -> PipelineInvocation | None: ...
    def create(self, invocation: PipelineInvocation) -> None: ...
    def claim_queued(
        self, worker_id: str, now: datetime
    ) -> PipelineInvocation | None: ...
    def mark_running(
        self, invocation_id: UUID, worker_id: str, now: datetime
    ) -> bool: ...
    def heartbeat(self, invocation_id: UUID, worker_id: str, now: datetime) -> bool: ...
    def finish(
        self,
        invocation_id: UUID,
        worker_id: str,
        state: str,
        finished_at: datetime,
        safe_error_code: str | None = None,
    ) -> bool: ...
    def reconcile(
        self, invocation_id: UUID, owner_id: str, finished_at: datetime
    ) -> bool: ...
