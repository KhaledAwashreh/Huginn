"""Exercise the real process boundary against disposable PostgreSQL."""

import json
import socket
import subprocess
import sys
import time
from urllib.error import URLError
from urllib.request import urlopen

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig


def test_real_uvicorn_health_readiness_and_openapi(management_database_url):
    expected = create_app(
        ManagementConfig(database_url=management_database_url)
    ).openapi()
    # Keep the chosen socket reserved across process startup.
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        port = listener.getsockname()[1]
        process = subprocess.Popen(
            [
                sys.executable,
                "-c",
                "import sys, uvicorn; "
                "from huginn.management.app import create_app; "
                "from huginn.management.config import ManagementConfig; "
                "uvicorn.run(create_app(ManagementConfig(database_url=sys.stdin.readline().strip())), "
                "fd=int(sys.argv[1]), log_level='error')",
                str(listener.fileno()),
            ],
            stdin=subprocess.PIPE,
            text=True,
            pass_fds=(listener.fileno(),),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
        try:
            assert process.stdin is not None
            process.stdin.write(management_database_url + "\n")
            process.stdin.close()
            process.stdin = None
            deadline = time.monotonic() + 10
            while True:
                try:
                    with urlopen(
                        f"http://127.0.0.1:{port}/health", timeout=0.2
                    ) as response:
                        assert response.status == 200
                        assert json.load(response) == {"status": "ok"}
                    break
                except URLError, TimeoutError:
                    assert process.poll() is None, (
                        "Uvicorn exited before becoming healthy"
                    )
                    assert time.monotonic() < deadline, "Uvicorn did not become healthy"
                    time.sleep(0.05)
            with urlopen(f"http://127.0.0.1:{port}/ready", timeout=5) as response:
                assert response.status == 200
                assert json.load(response) == {"status": "ready"}
            with urlopen(
                f"http://127.0.0.1:{port}/openapi.json", timeout=5
            ) as response:
                assert response.status == 200
                assert json.load(response) == expected
        finally:
            process.terminate()
            try:
                process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.communicate(timeout=5)
