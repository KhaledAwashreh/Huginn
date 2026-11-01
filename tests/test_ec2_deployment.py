"""Exercise the remote deployment entry point without touching Docker or EC2."""

import ast
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/deploy-ec2.py"
COMMIT = "a" * 40
PREVIOUS = "b" * 40
IMAGE = "ghcr.io/example/huginn@sha256:" + "c" * 64
IMAGE_ID = "sha256:" + "d" * 64
CONTAINER_ID = "e" * 64
COMPOSE = ["docker", "compose", "--env-file", ".env", "-f", "compose.yaml"]


@pytest.fixture
def deployment(tmp_path):
    checkout = tmp_path / "checkout"
    checkout.mkdir()
    (checkout / "scripts").mkdir()
    (checkout / "scripts/configure-compose.py").write_text(
        "def validate_https_configuration(config):\n"
        "    if config.get('error'): raise ValueError(config['error'])\n"
        "    return 'huginn.live' if 'traefik' in config['services'] else None\n"
    )
    original = (
        b"# keep operator settings\nPOSTGRES_PASSWORD=private-secret\n"
        b"HUGINN_IMAGE=old-image\nHUGINN_HOST_PORT=80\n"
        b"HUGINN_BIND_ADDRESS=0.0.0.0\n"
    )
    (checkout / ".env").write_bytes(original)
    binaries = tmp_path / "bin"
    binaries.mkdir()
    fake = binaries / "fake"
    fake.write_text(
        f"#!{sys.executable}\n"
        "import json, os, pathlib, sys\n"
        "state = pathlib.Path(os.environ['COMMAND_LOG'] + '.head')\n"
        "name = pathlib.Path(sys.argv[0]).name\n"
        "args = sys.argv[1:]\n"
        "if name == 'sudo':\n"
        "    name, args = args[1], args[2:]\n"
        "with open(os.environ['COMMAND_LOG'], 'a') as log:\n"
        "    log.write(json.dumps([name, *args]) + '\\n')\n"
        "if os.environ.get('EDIT_CONFIG_ON_FAILURE') and name == 'docker' and args[-1:] == ['pull'] and args[:1] == ['compose']:\n"
        "    pathlib.Path('.env').write_text('HUGINN_IMAGE=operator-image\\nPRIVATE_SETTING=operator-change\\n')\n"
        "    sys.exit(17)\n"
        "if os.environ.get('FAIL_COMMAND') == ' '.join([name, *args]):\n"
        "    sys.exit(17)\n"
        "if os.environ.get('FAIL_READINESS') and name == 'docker' and args[:6] == ['compose', '--env-file', '.env', '-f', 'compose.yaml', 'exec']:\n"
        "    sys.exit(19)\n"
        "if name == 'curl':\n"
        "    print(os.environ.get('HTTPS_RESPONSE', '{\"status\":\"ready\"}\\n200'))\n"
        "if name == 'docker' and args[-3:] == ['config', '--format', 'json']:\n"
        "    prior = not state.exists() or state.read_text() != '" + COMMIT + "'\n"
        "    if not prior and os.environ.get('FAIL_TARGET_CONFIG'): sys.exit(17)\n"
        "    print(os.environ.get('PREVIOUS_COMPOSE_CONFIG', os.environ.get('COMPOSE_CONFIG', '{\"services\":{}}')) if prior else os.environ.get('COMPOSE_CONFIG', '{\"services\":{}}'))\n"
        "if name == 'git':\n"
        "    if args[:2] == ['cat-file', '-e'] and os.environ.get('PREVIOUS_NO_HTTPS'): sys.exit(1)\n"
        "    if args[:1] == ['status']:\n"
        "        print(os.environ.get('DIRTY', '') or (' M compose.yaml\\n' if state.exists() and state.read_text() == '"
        + COMMIT
        + "' and os.environ.get('DIRTY_AFTER_CHECKOUT') else ''), end='')\n"
        "    elif args == ['rev-parse', 'HEAD']:\n"
        f"        print(state.read_text() if state.exists() else '{PREVIOUS}')\n"
        "    elif args == ['rev-parse', 'origin/master']:\n"
        f"        print(os.environ.get('LATEST', '{COMMIT}'))\n"
        "    elif args[:2] == ['checkout', '--detach']:\n"
        "        if os.environ.get('FAIL_ROLLBACK') and args[-1] == '"
        + PREVIOUS
        + "': sys.exit(23)\n"
        "        state.write_text(args[-1])\n"
        "        if os.environ.get('EDIT_CONFIG_ON_CHECKOUT') and args[-1] == '"
        + COMMIT
        + "': pathlib.Path('.env').write_text('HUGINN_IMAGE=operator-image\\nPRIVATE_SETTING=operator-change\\n')\n"
        "    elif args[:1] == ['diff']:\n"
        "        print(os.environ.get('PROXY_CHANGE', '') if args[-1:] == ['docker/traefik'] else os.environ.get('SCHEMA_CHANGE', ''), end='')\n"
        "elif name == 'docker' and args[:2] == ['image', 'inspect']:\n"
        f"    print('{IMAGE_ID}' if args[-1] == '{{{{.Id}}}}' else os.environ.get('IMAGE_COMMIT', '{COMMIT}'))\n"
        "elif name == 'docker' and args[:6] == ['compose', '--env-file', '.env', '-f', 'compose.yaml', 'ps']:\n"
        f"    print('{CONTAINER_ID}')\n"
        "elif name == 'docker' and args[:2] == ['container', 'inspect']:\n"
        f"    print(os.environ.get('RUNNING_IMAGE_ID', '{IMAGE_ID}'))\n"
    )
    fake.chmod(0o755)
    for name in ("git", "sudo", "curl"):
        (binaries / name).symlink_to(fake)
    log = tmp_path / "commands.jsonl"
    environment = {**os.environ, "PATH": f"{binaries}:{os.environ['PATH']}"}
    environment["COMMAND_LOG"] = str(log)

    def run(**changes):
        return subprocess.run(
            [sys.executable, str(SCRIPT), str(checkout), COMMIT, IMAGE],
            capture_output=True,
            text=True,
            env={**environment, **changes},
            timeout=10,
        )

    def commands():
        return [json.loads(line) for line in log.read_text().splitlines()]

    return checkout, original, run, commands


def test_deploy_pulls_exact_image_preserves_settings_and_checks_readiness(deployment):
    checkout, original, run, commands = deployment
    result = run()
    assert result.returncode == 0, result.stderr
    assert (checkout / ".env").read_bytes() == original.replace(
        b"HUGINN_IMAGE=old-image", f"HUGINN_IMAGE={IMAGE}".encode()
    )
    assert (checkout / ".env").stat().st_mode & 0o777 == 0o600
    calls = commands()
    assert ["docker", "pull", IMAGE] in calls
    assert ["git", "checkout", "--detach", COMMIT] in calls
    assert [*COMPOSE, "pull"] in calls
    assert [
        *COMPOSE,
        "up",
        "-d",
        "--no-build",
        "--wait",
        "--wait-timeout",
        "180",
    ] in calls
    assert any(call[:10] == [*COMPOSE, "exec", "-T", "app", "python"] for call in calls)
    assert "private-secret" not in result.stdout + result.stderr


@pytest.mark.parametrize(
    "changes,message",
    [
        ({"DIRTY": " M compose.yaml\n"}, "tracked changes"),
        ({"SCHEMA_CHANGE": "db/schema/new-table.sql\n"}, "schema"),
        ({"IMAGE_COMMIT": PREVIOUS}, "revision"),
    ],
)
def test_preflight_failure_leaves_config_and_containers_untouched(
    deployment, changes, message
):
    checkout, original, run, commands = deployment
    result = run(**changes)
    assert result.returncode != 0
    assert message in result.stderr
    assert (checkout / ".env").read_bytes() == original
    assert not any(call[:7] == [*COMPOSE, "up"] for call in commands())


def test_stale_workflow_does_not_replace_a_newer_release(deployment):
    checkout, original, run, commands = deployment
    result = run(LATEST="d" * 40)
    assert result.returncode == 0, result.stderr
    assert "Skipping" in result.stdout
    assert (checkout / ".env").read_bytes() == original
    assert not any(call[0] == "docker" for call in commands())


def test_missing_private_configuration_stops_before_deployment(deployment):
    checkout, _, run, _ = deployment
    (checkout / ".env").unlink()
    result = run()
    assert result.returncode != 0
    assert ".env" in result.stderr
    assert not (checkout / ".env").exists()


@pytest.mark.parametrize(
    "command",
    [
        f"docker pull {IMAGE}",
        "docker compose --env-file .env -f compose.yaml pull",
        "docker compose --env-file .env -f compose.yaml up -d --no-build --wait --wait-timeout 180",
    ],
)
def test_deployment_failure_is_reported_and_restores_previous_configuration(
    deployment, command
):
    checkout, original, run, _ = deployment
    result = run(FAIL_COMMAND=command)
    assert result.returncode != 0
    assert (checkout / ".env").read_bytes() == original
    assert "failed" in result.stderr.lower()


def test_missing_image_setting_is_added_without_changing_other_settings(deployment):
    checkout, original, run, _ = deployment
    original = original.replace(b"HUGINN_IMAGE=old-image\n", b"")
    (checkout / ".env").write_bytes(original)
    result = run()
    assert result.returncode == 0, result.stderr
    assert (
        checkout / ".env"
    ).read_bytes() == original + f"HUGINN_IMAGE={IMAGE}\n".encode()


def test_failed_readiness_restores_config_and_warns_containers_may_have_changed(
    deployment,
):
    checkout, original, run, commands = deployment
    result = run(FAIL_READINESS="1")
    assert result.returncode != 0
    assert (checkout / ".env").read_bytes() == original
    assert "Containers may have changed" in result.stderr
    assert ["git", "checkout", "--detach", PREVIOUS] in commands()


def test_running_container_must_use_the_published_image(deployment):
    checkout, original, run, commands = deployment
    result = run(RUNNING_IMAGE_ID="sha256:" + "f" * 64)
    assert result.returncode != 0
    assert "running app image" in result.stderr
    assert (checkout / ".env").read_bytes() == original
    assert "readiness check passed" not in result.stdout
    assert [
        "docker",
        "container",
        "inspect",
        CONTAINER_ID,
        "--format",
        "{{.Image}}",
    ] in commands()


def test_partial_checkout_stops_before_changing_config_or_containers(deployment):
    checkout, original, run, commands = deployment
    result = run(DIRTY_AFTER_CHECKOUT="1", FAIL_ROLLBACK="1")
    assert result.returncode != 0
    assert "clean checkout" in result.stderr
    assert "Rollback incomplete" in result.stderr
    assert "Previous checkout and .env restored" not in result.stderr
    assert (checkout / ".env").read_bytes() == original
    assert not any(call[:7] == [*COMPOSE, "up"] for call in commands())
    assert not any(
        "--force" in call or "-f" in call[1:] for call in commands() if call[0] == "git"
    )


def load_deployment_script():
    specification = importlib.util.spec_from_file_location("deployment_script", SCRIPT)
    module = importlib.util.module_from_spec(specification)
    specification.loader.exec_module(module)
    return module


def test_command_uses_remaining_aggregate_budget_and_stops_at_deadline(monkeypatch):
    module = load_deployment_script()
    clock = [100.0]
    observed = []
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])

    def run(arguments, **options):
        observed.append(options["timeout"])
        return subprocess.CompletedProcess(arguments, 0, "ok", "")

    monkeypatch.setattr(module, "run_command", run)
    assert module.command("git", "status", deadline=112.0) == "ok"
    assert observed == [12.0]
    clock[0] = 112.0
    with pytest.raises(RuntimeError, match="deadline"):
        module.command("git", "status", deadline=112.0)
    assert observed == [12.0]


def test_forward_deadline_reserves_time_to_restore_configuration(tmp_path, monkeypatch):
    module = load_deployment_script()
    original = b"HUGINN_IMAGE=previous\nPRIVATE_SETTING=preserve\n"
    (tmp_path / ".env").write_bytes(original)
    monkeypatch.chdir(tmp_path)
    clock = [0.0]
    current = [PREVIOUS]
    calls = []
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])

    def run(arguments, **options):
        calls.append((arguments, options["timeout"]))
        answer = ""
        if arguments[:2] == ("git", "fetch") or arguments[:4] == (
            "sudo",
            "-n",
            "docker",
            "pull",
        ):
            clock[0] += 300
        if arguments == ("git", "rev-parse", "HEAD"):
            answer = current[0]
        elif arguments == ("git", "rev-parse", "origin/master"):
            answer = COMMIT
        elif arguments[:2] == ("git", "checkout"):
            current[0] = arguments[-1]
        elif arguments[:5] == ("sudo", "-n", "docker", "image", "inspect"):
            answer = IMAGE_ID if arguments[-1] == "{{.Id}}" else COMMIT
        elif "up" in arguments:
            clock[0] += options["timeout"]
            raise subprocess.TimeoutExpired(arguments, options["timeout"])
        return subprocess.CompletedProcess(arguments, 0, answer, "")

    monkeypatch.setattr(module, "run_command", run)
    monkeypatch.setattr(module, "validate_hosted_configuration", lambda *args: None)
    original_run = run

    def run_with_config(arguments, **options):
        if arguments[-3:] == ("config", "--format", "json"):
            return subprocess.CompletedProcess(arguments, 0, '{"services":{}}', "")
        return original_run(arguments, **options)

    monkeypatch.setattr(module, "run_command", run_with_config)
    with pytest.raises(subprocess.TimeoutExpired):
        module.deploy(tmp_path, COMMIT, IMAGE)
    assert (tmp_path / ".env").read_bytes() == original
    assert current[0] == PREVIOUS
    assert clock[0] < 900
    rollback = [
        timeout
        for args, timeout in calls
        if args == ("git", "checkout", "--detach", PREVIOUS)
    ]
    assert rollback and 0 < rollback[0] <= 120
    assert all(timeout <= 600 for _, timeout in calls)


@pytest.mark.parametrize(
    "failure_stage", ["deployment", "checkout", "revision", "status"]
)
def test_unconfirmed_termination_stops_all_recovery(
    tmp_path, monkeypatch, capsys, failure_stage
):
    module = load_deployment_script()
    original = b"HUGINN_IMAGE=previous\nPRIVATE_SETTING=preserve\n"
    config = tmp_path / ".env"
    config.write_bytes(original)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sys, "argv", [str(SCRIPT), str(tmp_path), COMMIT, IMAGE])
    calls = []
    current = [PREVIOUS]
    failed = [False]
    uncertain_calls = []
    termination_error = module.CommandTerminationUnconfirmed

    def run(*arguments, deadline):
        assert not uncertain_calls, "no command may follow unconfirmed termination"
        calls.append(arguments)
        if "up" in arguments:
            failed[0] = True
            if failure_stage == "deployment":
                uncertain_calls.append(arguments)
                raise termination_error("termination could not be confirmed")
            raise RuntimeError("deployment failed")
        if failed[0] and (
            (failure_stage == "checkout" and arguments[:2] == ("git", "checkout"))
            or (failure_stage == "revision" and arguments[:2] == ("git", "rev-parse"))
            or (failure_stage == "status" and arguments[:2] == ("git", "status"))
        ):
            uncertain_calls.append(arguments)
            raise termination_error("termination could not be confirmed")
        if arguments == ("git", "rev-parse", "HEAD"):
            return current[0]
        if arguments == ("git", "rev-parse", "origin/master"):
            return COMMIT
        if arguments[:2] == ("git", "checkout"):
            current[0] = arguments[-1]
        if arguments[:5] == ("sudo", "-n", "docker", "image", "inspect"):
            return IMAGE_ID if arguments[-1] == "{{.Id}}" else COMMIT
        return ""

    monkeypatch.setattr(module, "validate_hosted_configuration", lambda *args: None)
    original_run = run

    def run_with_config(*arguments, deadline):
        if arguments[-3:] == ("config", "--format", "json"):
            return '{"services":{}}'
        return original_run(*arguments, deadline=deadline)

    monkeypatch.setattr(module, "command", run_with_config)
    assert module.main() == 1
    assert uncertain_calls
    assert config.read_bytes() == original.replace(
        b"HUGINN_IMAGE=previous", f"HUGINN_IMAGE={IMAGE}".encode()
    )
    assert current[0] == (
        PREVIOUS if failure_stage in {"revision", "status"} else COMMIT
    )
    if failure_stage == "deployment":
        assert ("git", "checkout", "--detach", PREVIOUS) not in calls
    output = capsys.readouterr()
    assert "manual inspection" in output.err.lower()
    assert "Previous checkout and .env restored" not in output.err
    assert "readiness check passed" not in output.out


def test_pinned_compose_file_ignores_an_untracked_override(tmp_path):
    if shutil.which("docker") is None:
        pytest.skip("Docker Compose is required to resolve deployment configuration")
    (tmp_path / "compose.yaml").write_text(
        "services:\n  app:\n    image: ${HUGINN_IMAGE}\n"
    )
    (tmp_path / "compose.override.yaml").write_text(
        "services:\n  app:\n    image: unexpected-override\n"
    )
    (tmp_path / ".env").write_text(f"HUGINN_IMAGE={IMAGE}\n")
    environment = {
        key: value
        for key, value in os.environ.items()
        if key not in {"HUGINN_IMAGE", "COMPOSE_FILE", "COMPOSE_ENV_FILES"}
    }
    result = subprocess.run(
        [*COMPOSE, "config", "--format", "json"],
        cwd=tmp_path,
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout)["services"]["app"]["image"] == IMAGE


def test_timed_out_command_stops_its_owned_descendants(tmp_path):
    import time

    module = load_deployment_script()
    started = tmp_path / "child-started"
    marker = tmp_path / "child-completed"
    child = (
        "import pathlib,time;pathlib.Path(" + repr(str(started)) + ").touch();"
        "time.sleep(1);pathlib.Path("
        + repr(str(marker))
        + ").write_text('still running')"
    )
    parent = (
        "import subprocess,sys,time;subprocess.Popen([sys.executable,'-c',"
        + repr(child)
        + "]);time.sleep(30)"
    )
    with pytest.raises(subprocess.TimeoutExpired):
        module.command(sys.executable, "-c", parent, deadline=time.monotonic() + 0.5)
    assert started.exists(), "the descendant must start before testing group cleanup"
    time.sleep(1.1)
    assert not marker.exists()


@pytest.mark.parametrize("kill_status", [0, 1])
def test_root_command_timeout_uses_bounded_privileged_group_cleanup(
    monkeypatch, kill_status
):
    module = load_deployment_script()
    cleanup = []

    class Process:
        pid = 98765
        calls = 0
        returncode = -9

        def communicate(self, *, timeout):
            self.calls += 1
            if self.calls == 1:
                raise subprocess.TimeoutExpired("sudo docker", timeout)
            assert timeout <= 5
            return "", ""

    def popen(arguments, **options):
        assert options["start_new_session"] is True
        return Process()

    def stop(arguments, **options):
        cleanup.append(arguments)
        assert options["timeout"] <= 5
        return subprocess.CompletedProcess(arguments, kill_status, "", "")

    monkeypatch.setattr(module.subprocess, "Popen", popen)
    monkeypatch.setattr(module.subprocess, "run", stop)
    expected = (
        subprocess.TimeoutExpired
        if kill_status == 0
        else module.CommandTerminationUnconfirmed
    )
    with pytest.raises(expected):
        module.run_command(("sudo", "-n", "docker", "compose"), timeout=1)
    assert cleanup == [["sudo", "-n", "kill", "-KILL", "--", "-98765"]]


@pytest.mark.parametrize(
    "change", ["EDIT_CONFIG_ON_CHECKOUT", "EDIT_CONFIG_ON_FAILURE"]
)
def test_operator_configuration_edits_are_preserved_when_deployment_fails(
    deployment, change
):
    checkout, _, run, commands = deployment
    result = run(**{change: "1"})
    assert result.returncode != 0
    assert (
        checkout / ".env"
    ).read_bytes() == b"HUGINN_IMAGE=operator-image\nPRIVATE_SETTING=operator-change\n"
    assert "preserv" in result.stderr.lower()
    assert "Previous checkout and .env restored" not in result.stderr
    if change == "EDIT_CONFIG_ON_CHECKOUT":
        assert not any(call[:7] == [*COMPOSE, "pull"] for call in commands())


@pytest.mark.parametrize(
    "path",
    [
        SCRIPT,
        SCRIPT.with_name("dispatch-ec2-deployment.py"),
        SCRIPT.with_name("configure-compose.py"),
    ],
)
def test_operator_scripts_parse_on_python_310(path):
    ast.parse(path.read_text(), filename=str(path), feature_version=(3, 10))


def test_https_readiness_uses_hostname_verification_and_loopback(monkeypatch):
    module = load_deployment_script()
    calls = []

    def run(*arguments, deadline):
        calls.append((arguments, deadline))
        return '{"status":"ready"}\n200'

    monkeypatch.setattr(module, "command", run)
    module.verify_https_readiness("huginn.live", deadline=module.time.monotonic() + 30)
    arguments, _ = calls[0]
    assert arguments[0] == "curl"
    assert "huginn.live:443:127.0.0.1" in arguments
    assert "https://huginn.live/ready" in arguments
    assert "--insecure" not in arguments and "-k" not in arguments
    assert "--location" not in arguments
    assert "--noproxy" in arguments


@pytest.mark.parametrize(
    "response", ['{"status":"ready"}\n302', '{"status":"wrong"}\n200', "not-json\n200"]
)
def test_https_readiness_rejects_wrong_response(monkeypatch, response):
    module = load_deployment_script()
    monkeypatch.setattr(module, "command", lambda *args, **kwargs: response)
    with pytest.raises(RuntimeError, match="HTTPS readiness"):
        module.verify_https_readiness(
            "huginn.live", deadline=module.time.monotonic() + 30
        )


def test_https_readiness_certificate_failure_exhausts_bounded_budget(monkeypatch):
    module = load_deployment_script()
    clock = [0.0]
    calls = []
    monkeypatch.setattr(module.time, "monotonic", lambda: clock[0])
    monkeypatch.setattr(
        module.time, "sleep", lambda seconds: clock.__setitem__(0, clock[0] + seconds)
    )

    def run(*arguments, deadline):
        calls.append(deadline)
        clock[0] += 1
        raise RuntimeError("curl certificate validation failed")

    monkeypatch.setattr(module, "command", run)
    with pytest.raises(RuntimeError, match="HTTPS readiness"):
        module.verify_https_readiness("huginn.live", deadline=7)
    assert calls and clock[0] <= 7
    assert all(deadline <= 7 for deadline in calls)


def test_https_readiness_never_retries_uncertain_termination(monkeypatch):
    module = load_deployment_script()
    calls = []

    def run(*arguments, deadline):
        calls.append(arguments)
        raise module.CommandTerminationUnconfirmed("not stopped")

    monkeypatch.setattr(module, "command", run)
    with pytest.raises(module.CommandTerminationUnconfirmed):
        module.verify_https_readiness(
            "huginn.live", deadline=module.time.monotonic() + 30
        )
    assert len(calls) == 1


HOSTED_CONFIG = json.dumps(
    {
        "services": {
            "traefik": {"environment": {"HUGINN_ACME_ENVIRONMENT": "production"}}
        }
    }
)


def test_hosted_release_preserves_profile_and_requires_verified_https(deployment):
    checkout, original, run, commands = deployment
    original += b"COMPOSE_PROFILES=https\nHUGINN_WEB_ORIGIN=https://huginn.live\n"
    (checkout / ".env").write_bytes(original)
    result = run(COMPOSE_CONFIG=HOSTED_CONFIG)
    assert result.returncode == 0, result.stderr
    assert (checkout / ".env").read_bytes() == original.replace(
        b"HUGINN_IMAGE=old-image", f"HUGINN_IMAGE={IMAGE}".encode()
    )
    assert any(call[0] == "curl" for call in commands())
    assert "verified HTTPS readiness passed" in result.stdout


def test_invalid_hosted_preflight_does_not_replace_services_or_secrets(deployment):
    checkout, original, run, commands = deployment
    invalid = json.loads(HOSTED_CONFIG)
    invalid["error"] = "HUGINN_WEB_ORIGIN must match HTTPS hostname"
    result = run(COMPOSE_CONFIG=json.dumps(invalid))
    assert result.returncode != 0
    assert "HUGINN_WEB_ORIGIN" in result.stderr
    assert (checkout / ".env").read_bytes() == original
    assert not any(call[:7] == [*COMPOSE, "up"] for call in commands())


def test_private_ready_cannot_hide_failed_https(deployment):
    checkout, original, run, commands = deployment
    result = run(COMPOSE_CONFIG=HOSTED_CONFIG, HTTPS_RESPONSE='{"status":"ready"}\n302')
    assert result.returncode != 0
    assert "HTTPS readiness" in result.stderr
    assert "readiness check passed" not in result.stdout
    assert (checkout / ".env").read_bytes() == original
    assert ["git", "checkout", "--detach", PREVIOUS] in commands()


def test_cutover_failure_preserves_https_checkout_instead_of_legacy_rollback(
    deployment,
):
    checkout, original, run, commands = deployment
    result = run(
        COMPOSE_CONFIG=HOSTED_CONFIG, PREVIOUS_NO_HTTPS="1", HTTPS_RESPONSE="{}\n200"
    )
    assert result.returncode != 0
    assert "previous revision cannot support active HTTPS" in result.stderr
    assert "Manual recovery" in result.stderr
    assert ["git", "checkout", "--detach", PREVIOUS] not in commands()
    assert (checkout / ".env").read_bytes() == original.replace(
        b"HUGINN_IMAGE=old-image", f"HUGINN_IMAGE={IMAGE}".encode()
    )
    assert not any("down" in call or "volume" in call for call in commands())


def test_staging_is_explicitly_rejected_by_automated_deployment(deployment):
    _, _, run, commands = deployment
    result = run(COMPOSE_CONFIG=HOSTED_CONFIG.replace("production", "staging"))
    assert result.returncode != 0
    assert "HUGINN_ACME_ENVIRONMENT" in result.stderr
    assert not any(call[:7] == [*COMPOSE, "up"] for call in commands())


def test_proxy_file_change_recreates_ingress_and_verifies_live_route(deployment):
    _, _, run, commands = deployment
    result = run(
        COMPOSE_CONFIG=HOSTED_CONFIG, PROXY_CHANGE="docker/traefik/dynamic.yaml"
    )
    assert result.returncode == 0, result.stderr
    recreate = [
        *COMPOSE,
        "up",
        "-d",
        "--no-build",
        "--no-deps",
        "--force-recreate",
        "--wait",
        "--wait-timeout",
        "60",
        "traefik",
    ]
    calls = commands()
    assert recreate in calls
    assert calls.index(recreate) < next(
        i for i, call in enumerate(calls) if call[0] == "curl"
    )


def test_unresolvable_configuration_does_not_restore_legacy_revision(deployment):
    checkout, original, run, commands = deployment
    result = run(
        PREVIOUS_NO_HTTPS="1",
        FAIL_TARGET_CONFIG="1",
    )
    assert result.returncode != 0
    assert ["git", "checkout", "--detach", PREVIOUS] not in commands()
    assert "Manual recovery" in result.stderr
    assert (checkout / ".env").read_bytes() == original


def test_active_https_cannot_be_removed_by_target_release(deployment):
    checkout, original, run, commands = deployment
    original += b"COMPOSE_PROFILES=https\nHUGINN_WEB_ORIGIN=https://huginn.live\n"
    (checkout / ".env").write_bytes(original)
    result = run(
        PREVIOUS_COMPOSE_CONFIG=HOSTED_CONFIG, COMPOSE_CONFIG='{"services":{}}'
    )
    assert result.returncode != 0
    assert "active HTTPS" in result.stderr
    assert "readiness check passed" not in result.stdout
    assert (checkout / ".env").read_bytes() == original
    assert not any(call[:7] == [*COMPOSE, "up"] for call in commands())
