import base64
import copy
import importlib.util
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/configure-compose.py"


def test_compose_configuration_generates_private_persistent_secrets(tmp_path):
    target = tmp_path / ".env.compose"
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target)],
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    values = dict(
        line.split("=", 1)
        for line in target.read_text().splitlines()
        if line and not line.startswith("#")
    )
    assert len(base64.urlsafe_b64decode(values["HUGINN_LIFECYCLE_PROOF_KEY"])) == 32
    assert len(bytes.fromhex(values["POSTGRES_PASSWORD"])) >= 24
    assert os.stat(target).st_mode & 0o777 == 0o600
    assert values["POSTGRES_PASSWORD"] not in result.stdout + result.stderr
    assert values["HUGINN_LIFECYCLE_PROOF_KEY"] not in result.stdout + result.stderr
    assert values["HUGINN_BOOTSTRAP_ADMIN_USERNAME"] == "Khaled"
    assert 8 <= len(values["HUGINN_BOOTSTRAP_ADMIN_PASSWORD"]) <= 16
    assert (
        values["HUGINN_BOOTSTRAP_ADMIN_PASSWORD"] not in result.stdout + result.stderr
    )
    assert values["HUGINN_BOOTSTRAP_SECOND_ADMIN_USERNAME"] == "Craig"
    second = values["HUGINN_BOOTSTRAP_SECOND_ADMIN_PASSWORD"]
    assert 8 <= len(second) <= 16
    assert second != values["HUGINN_BOOTSTRAP_ADMIN_PASSWORD"]
    assert second not in result.stdout + result.stderr
    original = target.read_bytes()
    again = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target)], capture_output=True
    )
    assert again.returncode != 0
    assert target.read_bytes() == original


def test_adding_admin_to_older_config_preserves_existing_secrets(tmp_path):
    target = tmp_path / ".env.compose"
    original = (
        "POSTGRES_PASSWORD=keep-db-password\nHUGINN_LIFECYCLE_PROOF_KEY=keep-key\n"
    )
    target.write_text(original)
    command = [sys.executable, str(SCRIPT), "--output", str(target), "--add-admin"]
    assert subprocess.run(command, capture_output=True).returncode == 0
    updated = target.read_text()
    assert updated.startswith(original)
    assert "HUGINN_BOOTSTRAP_ADMIN_USERNAME=Khaled" in updated
    assert subprocess.run(command, capture_output=True).returncode == 0
    assert target.read_text() == updated
    assert os.stat(target).st_mode & 0o777 == 0o600


def test_partial_admin_configuration_is_never_silently_replaced(tmp_path):
    target = tmp_path / ".env.compose"
    original = "HUGINN_BOOTSTRAP_ADMIN_PASSWORD=existing-password\n"
    target.write_text(original)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target), "--add-admin"],
        capture_output=True,
    )
    assert result.returncode != 0
    assert target.read_text() == original


def test_adding_second_admin_preserves_complete_existing_primary(tmp_path):
    target = tmp_path / ".env"
    original = (
        "POSTGRES_PASSWORD=keep-db\nHUGINN_LIFECYCLE_PROOF_KEY=keep-key\n"
        "HUGINN_BOOTSTRAP_ADMIN_USERNAME=existing-admin\n"
        "HUGINN_BOOTSTRAP_ADMIN_EMAIL=existing@example.test\n"
        "HUGINN_BOOTSTRAP_ADMIN_PASSWORD=KeepPassword!123\n"
    )
    target.write_text(original)
    command = [sys.executable, str(SCRIPT), "--output", str(target), "--add-admin"]
    assert subprocess.run(command, capture_output=True).returncode == 0
    updated = target.read_text()
    assert updated.startswith(original)
    assert "HUGINN_BOOTSTRAP_SECOND_ADMIN_USERNAME=Craig" in updated
    assert subprocess.run(command, capture_output=True).returncode == 0
    assert target.read_text() == updated


def test_partial_second_admin_never_changes_existing_file(tmp_path):
    target = tmp_path / ".env"
    original = "HUGINN_BOOTSTRAP_SECOND_ADMIN_PASSWORD=existing-password\n"
    target.write_text(original)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target), "--add-admin"],
        capture_output=True,
    )
    assert result.returncode != 0
    assert target.read_text() == original


def test_complete_but_empty_admin_setting_is_rejected_without_changes(tmp_path):
    target = tmp_path / ".env"
    original = (
        "HUGINN_BOOTSTRAP_ADMIN_USERNAME=Khaled\n"
        "HUGINN_BOOTSTRAP_ADMIN_EMAIL=khaled@example.test\n"
        "HUGINN_BOOTSTRAP_ADMIN_PASSWORD=\n"
    )
    target.write_text(original)
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target), "--add-admin"],
        capture_output=True,
    )
    assert result.returncode != 0
    assert target.read_text() == original


@pytest.mark.parametrize(
    "image",
    (
        None,
        "ghcr.io/example/huginn:" + "a" * 40,
        "ghcr.io/example/huginn@sha256:" + "b" * 64,
    ),
)
def test_compose_resolves_shared_image_without_changing_infrastructure(tmp_path, image):
    if shutil.which("docker") is None:
        pytest.skip(
            "Docker Compose is required to resolve the deployment configuration"
        )
    target = tmp_path / ".env"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target)],
        check=True,
        capture_output=True,
    )
    # Exercise the fallback independently of the generated template default.
    target.write_text(
        "\n".join(
            line
            for line in target.read_text().splitlines()
            if not line.startswith("HUGINN_IMAGE=")
        )
        + "\n"
    )
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("HUGINN_") and key != "POSTGRES_PASSWORD"
    }
    if image is not None:
        environment["HUGINN_IMAGE"] = image
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(target),
            "--profile",
            "jobs",
            "config",
            "--format",
            "json",
        ],
        cwd=SCRIPT.parents[1],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    services = json.loads(result.stdout)["services"]
    for name in (
        "app",
        "admin-seed",
        "collection-worker",
        "matching-worker",
        "mail-worker",
        "weekly-digest",
    ):
        assert services[name]["image"] == (image or "huginn-app:local"), name
    assert services["db"]["image"] == "postgres:16-alpine"
    assert services["mailpit"]["image"] == "axllent/mailpit:v1.27.10"


def _compose_environment():
    return {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("HUGINN_")
        and key not in {"POSTGRES_PASSWORD", "COMPOSE_PROFILES"}
    }


def _resolved_compose(tmp_path, **values):
    target = tmp_path / ".env"
    subprocess.run(
        [sys.executable, str(SCRIPT), "--output", str(target)],
        check=True,
        capture_output=True,
    )
    with target.open("a") as stream:
        for key, value in values.items():
            stream.write(f"{key}={value}\n")
    environment = {
        key: value
        for key, value in os.environ.items()
        if not key.startswith("HUGINN_")
        and key not in {"POSTGRES_PASSWORD", "COMPOSE_PROFILES"}
    }
    result = subprocess.run(
        [
            "docker",
            "compose",
            "--env-file",
            str(target),
            "-f",
            str(SCRIPT.parents[1] / "compose.yaml"),
            "config",
            "--format",
            "json",
        ],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    return target, json.loads(result.stdout)


def _hosted_settings():
    return {
        "COMPOSE_PROFILES": "https",
        "HUGINN_DOMAIN": "huginn.live",
        "HUGINN_DOMAIN_ALIAS": "www.huginn.live",
        "HUGINN_ACME_EMAIL": "owner@example.com",
        "HUGINN_WEB_ORIGIN": "https://huginn.live",
        "HUGINN_MANAGEMENT_ENVIRONMENT": "production",
        "HUGINN_BIND_ADDRESS": "127.0.0.1",
        "HUGINN_INGRESS_SUBNET": "172.30.255.0/29",
    }


def test_local_compose_does_not_activate_ingress(tmp_path):
    target, config = _resolved_compose(tmp_path)
    assert "traefik" not in config["services"]
    assert not config["networks"]["ingress"]["ipam"]["config"][0].get("subnet")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--output", str(target)],
        env=_compose_environment(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"https": False, "domain": None}


def test_hosted_compose_uses_private_upstream_and_pinned_ingress(tmp_path):
    _, config = _resolved_compose(tmp_path, **_hosted_settings())
    services = config["services"]
    proxy = services["traefik"]
    assert proxy["image"].startswith("traefik:v3.7.17@sha256:")
    assert {port["published"] for port in proxy["ports"]} == {"80", "443"}
    assert services["app"]["ports"][0]["host_ip"] == "127.0.0.1"
    assert services["app"]["environment"]["FORWARDED_ALLOW_IPS"] == "172.30.255.2"
    assert proxy["networks"]["ingress"]["ipv4_address"] == "172.30.255.2"
    assert set(proxy["networks"]) == {"ingress"}
    assert all("docker.sock" not in mount["target"] for mount in proxy["volumes"])
    for name, service in services.items():
        if name not in {"app", "traefik"}:
            assert "ingress" not in service.get("networks", {})
    for name in ("app", "mail-worker", "matching-worker", "collection-worker"):
        assert (
            services[name]["environment"]["HUGINN_WEB_ORIGIN"] == "https://huginn.live"
        )
        assert (
            services[name]["environment"]["HUGINN_MANAGEMENT_ENVIRONMENT"]
            == "production"
        )


@pytest.mark.parametrize(
    "key,value",
    [
        ("HUGINN_DOMAIN", ""),
        ("HUGINN_DOMAIN_ALIAS", "bad/host"),
        ("HUGINN_ACME_EMAIL", ""),
        ("HUGINN_ACME_EMAIL", "owner@example..com"),
        ("HUGINN_ACME_EMAIL", "owner@-example.com"),
        ("HUGINN_ACME_EMAIL", "owner@example-.com"),
        ("HUGINN_ACME_EMAIL", "owner@example_com.test"),
        ("HUGINN_WEB_ORIGIN", "http://huginn.live"),
        ("HUGINN_WEB_ORIGIN", "https://other.live"),
        ("HUGINN_BIND_ADDRESS", "0.0.0.0"),
        ("HUGINN_PROXY_IP", "0.0.0.0/0"),
        ("HUGINN_INGRESS_SUBNET", ""),
        ("HUGINN_MANAGEMENT_ENVIRONMENT", "local"),
        ("HUGINN_ACME_ENVIRONMENT", "invalid"),
    ],
)
def test_hosted_preflight_rejects_invalid_settings_without_rewriting(
    tmp_path, key, value
):
    settings = _hosted_settings()
    settings[key] = value
    target, _ = _resolved_compose(tmp_path, **settings)
    original = target.read_bytes()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--output", str(target)],
        env=_compose_environment(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 1, result.stdout + result.stderr
    assert key in result.stderr
    assert target.read_bytes() == original


def test_hosted_preflight_accepts_consistent_settings_without_rewriting(tmp_path):
    target, _ = _resolved_compose(tmp_path, **_hosted_settings())
    original = target.read_bytes()
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--output", str(target)],
        env=_compose_environment(),
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"https": True, "domain": "huginn.live"}
    assert target.read_bytes() == original


def test_preflight_trust_and_network_boundaries(tmp_path):
    spec = importlib.util.spec_from_file_location("configure_compose", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, config = _resolved_compose(tmp_path, **_hosted_settings())
    assert module.validate_https_configuration(config) == "huginn.live"
    modified = copy.deepcopy(config)
    modified["services"]["app"]["environment"]["FORWARDED_ALLOW_IPS"] = "*"
    with pytest.raises(ValueError, match="HUGINN_PROXY_IP"):
        module.validate_https_configuration(modified)
    modified = copy.deepcopy(config)
    modified["networks"]["ingress"]["ipam"]["config"][0]["subnet"] = "172.30.0.0/16"
    with pytest.raises(ValueError, match="HUGINN_INGRESS_SUBNET"):
        module.validate_https_configuration(modified)
    modified = copy.deepcopy(config)
    modified["services"]["mail-worker"]["networks"]["ingress"] = {}
    with pytest.raises(ValueError, match="Only app and traefik"):
        module.validate_https_configuration(modified)
    modified = copy.deepcopy(config)
    del modified["services"]["app"]["networks"]["ingress"]
    with pytest.raises(ValueError, match="app must attach to the ingress network"):
        module.validate_https_configuration(modified)


def test_preflight_uses_private_file_despite_exported_compose_settings(tmp_path):
    target, _ = _resolved_compose(tmp_path, **_hosted_settings())
    original = target.read_bytes()
    environment = _compose_environment() | {
        "COMPOSE_PROFILES": "jobs",
        "HUGINN_WEB_ORIGIN": "http://shell-override.example",
        "HUGINN_ACME_EMAIL": "",
        "POSTGRES_PASSWORD": "shell-password",
    }
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--check", "--output", str(target)],
        env=environment,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stderr
    assert json.loads(result.stdout) == {"https": True, "domain": "huginn.live"}
    assert target.read_bytes() == original


@pytest.mark.parametrize(
    "subnet,address",
    [
        ("172.30.255.0/30", "172.30.255.2"),
        ("172.30.255.0/29", "172.30.255.1"),
        ("127.0.0.0/29", "127.0.0.2"),
        ("169.254.0.0/29", "169.254.0.2"),
    ],
)
def test_preflight_rejects_unusable_proxy_networks(tmp_path, subnet, address):
    spec = importlib.util.spec_from_file_location("configure_compose", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _, config = _resolved_compose(tmp_path, **_hosted_settings())
    config["networks"]["ingress"]["ipam"]["config"][0]["subnet"] = subnet
    config["services"]["traefik"]["environment"]["HUGINN_PROXY_IP"] = address
    config["services"]["traefik"]["networks"]["ingress"]["ipv4_address"] = address
    config["services"]["app"]["environment"]["FORWARDED_ALLOW_IPS"] = address
    with pytest.raises(ValueError, match="HUGINN_INGRESS_SUBNET"):
        module.validate_https_configuration(config)
