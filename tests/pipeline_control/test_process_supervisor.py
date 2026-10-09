import os
import sys

import pytest

from huginn.pipeline_control.infrastructure.process_supervisor import (
    ProcessExecutorSupervisor,
    current_identity,
    new_execution_owner,
)


class Guard:
    def __init__(self, fail=False):
        self.fail = fail
        self.attached = None
        self.beats = 0

    def attach_executor(self, owner_id, identity):
        self.attached = identity

    def heartbeat(self, owner_id):
        self.beats += 1
        if self.fail:
            raise RuntimeError("private connection failure")


def test_real_child_waits_for_durable_identity_and_is_reaped_after_guard_loss():
    guard = Guard(fail=True)
    supervisor = ProcessExecutorSupervisor(
        command=(
            sys.executable,
            "-c",
            'import json,os,sys,time; from huginn.pipeline_control.infrastructure.process_supervisor import current_identity; from dataclasses import asdict; print(json.dumps(asdict(current_identity())),flush=True); assert sys.stdin.readline()=="GO\\n"; time.sleep(30)',
        ),
        heartbeat_seconds=0.05,
        termination_grace_seconds=0.1,
    )
    with pytest.raises(RuntimeError):
        supervisor.run(new_execution_owner(None), guard)
    assert guard.attached is not None
    assert not os.path.exists(f"/proc/{guard.attached.pid}")


def test_trusted_child_handshake_completes_and_records_identity():
    guard = Guard()
    supervisor = ProcessExecutorSupervisor(
        command=(
            sys.executable,
            "-c",
            'import json,sys; from huginn.pipeline_control.infrastructure.process_supervisor import current_identity; from dataclasses import asdict; print(json.dumps(asdict(current_identity())),flush=True); assert sys.stdin.readline()=="GO\\n"',
        ),
        heartbeat_seconds=0.05,
    )
    assert supervisor.run(new_execution_owner(None), guard) == 0
    assert guard.attached.host == current_identity().host
    assert guard.beats >= 1
