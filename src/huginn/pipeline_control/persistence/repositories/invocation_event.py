from uuid import uuid4

from huginn.management.persistence.contracts.database import (
    DatabaseSession,
    JsonParameter,
)
from huginn.pipeline_control.domain.value_objects.pipeline_event import PipelineEvent


class PostgresInvocationEventRepository:
    def __init__(self, connection: DatabaseSession) -> None:
        self.connection = connection

    def append(self, event: PipelineEvent, transition_key: str) -> None:
        self.connection.execute(
            "SELECT id FROM ops.pipeline_invocations WHERE id = %s FOR UPDATE",
            (event.invocation_id,),
        ).fetchone()
        row = self.connection.execute(
            "SELECT COALESCE(MAX(sequence), 0) + 1 FROM ops.pipeline_invocation_events WHERE invocation_id = %s",
            (event.invocation_id,),
        ).fetchone()
        metrics = [
            {"kind": metric.kind, "unit": metric.unit, "value": metric.value}
            for metric in event.metrics
        ]
        self.connection.execute(
            "INSERT INTO ops.pipeline_invocation_events "
            "(id, invocation_id, sequence, occurred_at, kind, transition_key, stage_name, source_name, safe_code, safe_message, metrics) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (invocation_id, transition_key) DO NOTHING",
            (
                uuid4(),
                event.invocation_id,
                row[0],
                event.occurred_at,
                event.kind,
                transition_key,
                event.stage_name,
                event.source_name,
                event.safe_code,
                event.safe_message,
                JsonParameter(metrics),
            ),
        )
