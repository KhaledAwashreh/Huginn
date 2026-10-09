from datetime import datetime, timedelta
from math import ceil
from uuid import UUID

from huginn.management.persistence.contracts.database import DatabaseSession


class PostgresTriggerThrottleRepository:
    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    def reserve(
        self, requester_account_id: UUID, request_id: UUID, now: datetime, limit: int
    ) -> int | None:
        window_start = now - timedelta(hours=1)
        self.connection.execute(
            "DELETE FROM ops.pipeline_trigger_throttle "
            "WHERE requester_account_id = %s AND requested_at <= %s",
            (requester_account_id, window_start),
        )
        row = self.connection.execute(
            "SELECT COUNT(*), MIN(requested_at) FROM ops.pipeline_trigger_throttle "
            "WHERE requester_account_id = %s AND requested_at > %s",
            (requester_account_id, window_start),
        ).fetchone()
        count, oldest = row
        if count >= limit:
            seconds = (oldest + timedelta(hours=1) - now).total_seconds()
            return max(1, ceil(seconds))
        self.connection.execute(
            "INSERT INTO ops.pipeline_trigger_throttle (requester_account_id, request_id, requested_at) "
            "VALUES (%s, %s, %s) ON CONFLICT (requester_account_id, request_id) DO NOTHING",
            (requester_account_id, request_id, now),
        )
        return None
