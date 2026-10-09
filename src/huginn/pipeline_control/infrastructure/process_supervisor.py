"""Trusted process-group supervision. Pipeline control design section 5."""

import ctypes
import json
import os
import selectors
import signal
import socket
import subprocess
import sys
import threading
import time
from contextlib import suppress
from pathlib import Path
from uuid import UUID, uuid4

from huginn.pipeline_control.application.errors.execution import (
    ExecutorTerminationUnprovenError,
    TrackingUncertainError,
)
from huginn.pipeline_control.application.protocols.execution_guard import ExecutionGuard
from huginn.pipeline_control.application.read_models.executor_identity import (
    ExecutorIdentity,
)
from huginn.pipeline_control.domain.value_objects.execution_owner import ExecutionOwner


def process_start(pid: int) -> str | None:
    try:
        fields = Path(f"/proc/{pid}/stat").read_text().rsplit(")", 1)[1].split()
        boot_id = Path("/proc/sys/kernel/random/boot_id").read_text().strip()
        return f"{boot_id}:{fields[19]}"
    except OSError, IndexError:
        return None


def current_identity() -> ExecutorIdentity:
    return ExecutorIdentity(
        socket.gethostname(), os.getpid(), process_start(os.getpid()) or ""
    )


def new_execution_owner(invocation_id: UUID | None) -> ExecutionOwner:
    identity = current_identity()
    return ExecutionOwner(
        uuid4(),
        uuid4(),
        invocation_id,
        identity.host,
        identity.pid,
        identity.started_at,
    )


def group_members(group_id: int) -> tuple[int, ...]:
    members = []
    for entry in Path("/proc").iterdir():
        if not entry.name.isdigit():
            continue
        try:
            fields = (entry / "stat").read_text().rsplit(")", 1)[1].split()
            if int(fields[2]) == group_id and fields[0] != "Z":
                members.append(int(entry.name))
        except OSError, ValueError, IndexError:
            continue
    return tuple(members)


def prove_stopped(owner: ExecutionOwner, executor: ExecutorIdentity | None) -> bool:
    if owner.host != socket.gethostname():
        return False
    if process_start(owner.supervisor_pid) == owner.supervisor_started_at:
        return False
    if executor is not None:
        if executor.host != socket.gethostname():
            return False
        if process_start(executor.pid) == executor.started_at:
            return False
        if group_members(executor.pid):
            return False
    return True


class ProcessExecutorSupervisor:
    def __init__(
        self,
        *,
        command: tuple[str, ...] | None = None,
        heartbeat_seconds: float = 15,
        termination_grace_seconds: float = 5,
        handshake_seconds: float = 5,
        stop_event: threading.Event | None = None,
    ) -> None:
        if ctypes.CDLL(None, use_errno=True).prctl(36, 1, 0, 0, 0) != 0:
            raise ExecutorTerminationUnprovenError("subreaper_unavailable")
        self._command = command
        self._heartbeat_seconds = heartbeat_seconds
        self._termination_grace_seconds = termination_grace_seconds
        self._handshake_seconds = handshake_seconds
        self._stop_event = stop_event or threading.Event()

    def prove_stopped(
        self, owner: ExecutionOwner, executor: ExecutorIdentity | None
    ) -> bool:
        return prove_stopped(owner, executor)

    def _terminate(self, process: subprocess.Popen) -> None:
        for sig in (signal.SIGTERM, signal.SIGKILL):
            if group_members(process.pid):
                with suppress(ProcessLookupError):
                    os.killpg(process.pid, sig)
            deadline = time.monotonic() + self._termination_grace_seconds
            while group_members(process.pid) and time.monotonic() < deadline:
                time.sleep(0.02)
            if not group_members(process.pid):
                break
        try:
            process.wait(timeout=self._termination_grace_seconds)
        except subprocess.TimeoutExpired:
            raise ExecutorTerminationUnprovenError("executor_stop_unproven") from None
        while True:
            try:
                reaped, _ = os.waitpid(-process.pid, os.WNOHANG)
            except ChildProcessError:
                break
            if reaped == 0:
                break
        if group_members(process.pid):
            raise ExecutorTerminationUnprovenError("executor_stop_unproven")

    def run(self, owner: ExecutionOwner, guard: ExecutionGuard) -> int:
        command = self._command or (
            sys.executable,
            "-m",
            "huginn.pipeline_control.presentation.cli.executor",
            "--invocation-id",
            str(owner.invocation_id) if owner.invocation_id else "standalone",
        )
        process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=None,
            start_new_session=True,
            text=True,
            bufsize=1,
        )
        stop = threading.Event()
        failures = []
        thread = None

        def heartbeat():
            while not stop.wait(self._heartbeat_seconds):
                try:
                    guard.heartbeat(owner.owner_id)
                except Exception:
                    failures.append(True)
                    return

        try:
            with selectors.DefaultSelector() as selector:
                selector.register(process.stdout, selectors.EVENT_READ)
                deadline = time.monotonic() + self._handshake_seconds
                handshake = b""
                while b"\n" not in handshake:
                    remaining = deadline - time.monotonic()
                    if remaining <= 0 or not selector.select(remaining):
                        raise TrackingUncertainError("executor_handshake_missing")
                    chunk = os.read(process.stdout.fileno(), 4096)
                    if not chunk or len(handshake) + len(chunk) > 4096:
                        raise TrackingUncertainError("executor_handshake_invalid")
                    handshake += chunk
                data = json.loads(handshake.split(b"\n", 1)[0])
            identity = ExecutorIdentity(**data)
            if (
                identity.host != owner.host
                or identity.pid != process.pid
                or identity.started_at != process_start(process.pid)
            ):
                raise TrackingUncertainError("executor_identity_invalid")
            guard.attach_executor(owner.owner_id, identity)
            guard.heartbeat(owner.owner_id)
            process.stdin.write("GO\n")
            process.stdin.flush()
            process.stdin.close()
            thread = threading.Thread(
                target=heartbeat, daemon=True, name="pipeline-heartbeat"
            )
            thread.start()
            while process.poll() is None:
                if failures or self._stop_event.is_set():
                    raise TrackingUncertainError("execution_guard_lost")
                time.sleep(0.02)
            if failures:
                raise TrackingUncertainError("execution_guard_lost")
            self._terminate(process)
            guard.heartbeat(owner.owner_id)
            return process.returncode
        except BaseException:
            self._terminate(process)
            raise
        finally:
            stop.set()
            if thread is not None:
                thread.join(timeout=3)
                if thread.is_alive():
                    raise ExecutorTerminationUnprovenError("heartbeat_stop_unproven")
            for stream in (process.stdin, process.stdout):
                if stream is not None and not stream.closed:
                    stream.close()
