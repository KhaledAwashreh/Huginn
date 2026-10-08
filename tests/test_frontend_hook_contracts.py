from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
ZERO_OID = "0" * 40


def _git(repo: Path, *arguments: str) -> str:
    result = subprocess.run(
        ["git", *arguments],
        cwd=repo,
        check=True,
        capture_output=True,
        text=True,
    )
    return result.stdout.strip()


def _make_repo(tmp_path: Path) -> tuple[Path, Path, Path]:
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(repo, "init", "--initial-branch=master")
    _git(repo, "config", "user.email", "test@example.invalid")
    _git(repo, "config", "user.name", "Hook test")

    scripts = repo / "scripts"
    scripts.mkdir()
    for script in ("pre-commit-review.sh", "pre-push-review.sh", "frontend-review.sh"):
        shutil.copy2(PROJECT_ROOT / "scripts" / script, scripts / script)

    frontend = repo / "frontend"
    frontend.mkdir()
    (frontend / ".node-version").write_text("24.21.0\n")
    (frontend / "package.json").write_text('{"packageManager":"npm@12.2.0"}\n')
    (frontend / "package-lock.json").write_text("{}\n")
    binaries = frontend / "node_modules" / ".bin"
    binaries.mkdir(parents=True)
    for name in ("eslint", "prettier", "playwright"):
        binary = binaries / name
        binary.write_text("#!/bin/sh\nexit 0\n")
        binary.chmod(0o755)

    (repo / "README.md").write_text("base\n")
    _git(repo, "add", ".")
    _git(repo, "commit", "-m", "base")
    base = _git(repo, "rev-parse", "HEAD")
    _git(repo, "update-ref", "refs/remotes/origin/master", base)
    _git(repo, "switch", "-c", "topic")
    return repo, frontend, scripts


def _environment(
    tmp_path: Path,
    *,
    node_version: str | None = "v24.21.0",
    npm_version: str | None = "12.2.0",
) -> tuple[dict[str, str], Path]:
    binaries = tmp_path / "bin"
    binaries.mkdir(parents=True)
    for name in ("git", "sed", "bash", "mktemp", "rm"):
        actual = shutil.which(name)
        assert actual is not None
        (binaries / name).symlink_to(actual)

    (binaries / "uv").write_text("#!/bin/sh\nexit 0\n")
    (binaries / "uv").chmod(0o755)
    npm_log = tmp_path / "npm.log"
    if node_version is not None:
        node = binaries / "node"
        node.write_text('#!/bin/sh\nprintf "%s\\n" "$FAKE_NODE_VERSION"\n')
        node.chmod(0o755)
    if npm_version is not None:
        npm = binaries / "npm"
        npm.write_text(
            "#!/bin/sh\n"
            'if [ "${1:-}" = "--version" ]; then printf "%s\\n" "$FAKE_NPM_VERSION"; exit 0; fi\n'
            'printf "%s\\n" "$*" >> "$FAKE_NPM_LOG"\n'
        )
        npm.chmod(0o755)

    environment = {
        "PATH": str(binaries),
        "FAKE_NODE_VERSION": node_version or "",
        "FAKE_NPM_VERSION": npm_version or "",
        "FAKE_NPM_LOG": str(npm_log),
        "HUGINN_PRE_PUSH_BASE_REF": "origin/master",
    }
    return environment, npm_log


def _commit_change(repo: Path, relative_path: str) -> str:
    changed_file = repo / relative_path
    changed_file.parent.mkdir(parents=True, exist_ok=True)
    changed_file.write_text("changed\n")
    _git(repo, "add", relative_path)
    _git(repo, "commit", "-m", "change")
    return _git(repo, "rev-parse", "HEAD")


def _run_hook(
    repo: Path, script: str, environment: dict[str, str], push_line: str = ""
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["/bin/bash", str(repo / "scripts" / script)],
        cwd=repo,
        env={**os.environ, **environment},
        input=push_line,
        capture_output=True,
        text=True,
        check=False,
    )


def _push_line(local_oid: str) -> str:
    return f"refs/heads/topic {local_oid} refs/heads/topic {ZERO_OID}\n"


def _push_line_with_remote(local_oid: str, remote_oid: str) -> str:
    return f"refs/heads/topic {local_oid} refs/heads/topic {remote_oid}\n"


def test_pre_push_does_not_require_node_for_python_only_changes(tmp_path: Path) -> None:
    repo, _, _ = _make_repo(tmp_path)
    local_oid = _commit_change(repo, "src/huginn/gold/example.py")
    environment, npm_log = _environment(tmp_path, node_version=None, npm_version=None)

    result = _run_hook(repo, "pre-push-review.sh", environment, _push_line(local_oid))

    assert result.returncode == 0, result.stdout + result.stderr
    assert (
        "No frontend or management/pipeline API schema paths changed" in result.stdout
    )
    assert not npm_log.exists()


def test_pre_push_runs_schema_gate_and_browser_gate_for_frontend_features(
    tmp_path: Path,
) -> None:
    repo, _, _ = _make_repo(tmp_path)
    local_oid = _commit_change(
        repo, "frontend/src/features/session/pages/LoginPage.vue"
    )
    environment, npm_log = _environment(tmp_path)

    result = _run_hook(repo, "pre-push-review.sh", environment, _push_line(local_oid))

    assert result.returncode == 0, result.stdout + result.stderr
    commands = npm_log.read_text().splitlines()
    assert "--prefix frontend run check" in commands
    assert "--prefix frontend run test:e2e" in commands


def test_pre_push_runs_schema_gate_without_browser_for_api_schema_only(
    tmp_path: Path,
) -> None:
    repo, _, _ = _make_repo(tmp_path)
    local_oid = _commit_change(
        repo,
        "src/huginn/management/presentation/api/responses/example.py",
    )
    environment, npm_log = _environment(tmp_path)

    result = _run_hook(repo, "pre-push-review.sh", environment, _push_line(local_oid))

    assert result.returncode == 0, result.stdout + result.stderr
    commands = npm_log.read_text().splitlines()
    assert "--prefix frontend run check" in commands
    assert all("test:e2e" not in command for command in commands)


def test_pre_push_runs_schema_gate_for_pipeline_control_changes(tmp_path: Path) -> None:
    repo, _, _ = _make_repo(tmp_path)
    local_oid = _commit_change(
        repo,
        "src/huginn/pipeline_control/application/services/invocation.py",
    )
    environment, npm_log = _environment(tmp_path)

    result = _run_hook(repo, "pre-push-review.sh", environment, _push_line(local_oid))

    assert result.returncode == 0, result.stdout + result.stderr
    assert "--prefix frontend run check" in npm_log.read_text().splitlines()


def test_pre_push_runs_browser_gate_for_authentication_changes(tmp_path: Path) -> None:
    repo, _, _ = _make_repo(tmp_path)
    local_oid = _commit_change(
        repo,
        "src/huginn/management/application/services/authentication.py",
    )
    environment, npm_log = _environment(tmp_path)

    result = _run_hook(repo, "pre-push-review.sh", environment, _push_line(local_oid))

    assert result.returncode == 0, result.stdout + result.stderr
    commands = npm_log.read_text().splitlines()
    assert "--prefix frontend run check" in commands
    assert "--prefix frontend run test:e2e" in commands


def test_pre_push_fails_closed_when_remote_commit_is_unknown(tmp_path: Path) -> None:
    repo, _, _ = _make_repo(tmp_path)
    local_oid = _commit_change(repo, "src/huginn/gold/example.py")
    environment, npm_log = _environment(tmp_path, node_version=None, npm_version=None)

    result = _run_hook(
        repo,
        "pre-push-review.sh",
        environment,
        _push_line_with_remote(local_oid, "f" * 40),
    )

    assert result.returncode != 0
    assert "Cannot diff pushed commits" in result.stderr
    assert not npm_log.exists()


def test_pre_commit_checks_only_staged_frontend_files_and_enforces_pins(
    tmp_path: Path,
) -> None:
    repo, frontend, _ = _make_repo(tmp_path)
    (frontend / "src.ts").write_text("staged\n")
    _git(repo, "add", "frontend/src.ts")
    environment, npm_log = _environment(tmp_path)

    result = _run_hook(repo, "pre-commit-review.sh", environment)

    assert result.returncode == 0, result.stdout + result.stderr
    commands = npm_log.read_text().splitlines()
    assert "--prefix frontend run lint" in commands
    assert "--prefix frontend run format:check" in commands

    mismatched_environment, mismatched_log = _environment(
        tmp_path / "mismatch",
        node_version="v22.0.0",
    )
    mismatch = _run_hook(repo, "pre-commit-review.sh", mismatched_environment)
    assert mismatch.returncode != 0
    assert "require Node v24.21.0 and npm 12.2.0" in mismatch.stderr
    assert not mismatched_log.exists()
