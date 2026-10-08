"""Optional same-origin delivery, web-ui-foundation design section 4."""

from fastapi.testclient import TestClient

from huginn.management.app import create_app
from huginn.management.config import ManagementConfig


def test_spa_deep_links_preserve_api_docs_and_missing_assets(tmp_path):
    (tmp_path / "assets").mkdir()
    (tmp_path / "index.html").write_text("<html>Huginn shell</html>")
    (tmp_path / "assets" / "app-AbCd1234.js").write_text("console.log('app')")
    app = create_app(
        ManagementConfig(
            "postgresql://unused:unused@127.0.0.1:1/unused",
            frontend_assets_path=tmp_path,
        ),
    )
    client = TestClient(app)
    assert client.get("/account").text == "<html>Huginn shell</html>"
    assert client.get("/account").headers["cache-control"] == "no-store"
    asset = client.get("/assets/app-AbCd1234.js")
    assert asset.status_code == 200
    assert "immutable" in asset.headers["cache-control"]
    for path in (
        "/api/not-a-route",
        "/api",
        "/assets/missing.js",
        "/missing.js",
        "/docs/not-a-route",
        "/redoc/not-a-route",
        "/health/not-a-route",
        "/ready/not-a-route",
        "/openapi.json/not-a-route",
    ):
        response = client.get(path)
        assert response.status_code == 404, path
        assert "Huginn shell" not in response.text
    assert client.get("/health").json() == {"status": "ok"}
    assert client.get("/docs").status_code == 200
    assert client.get("/openapi.json").json()["openapi"]


def test_missing_frontend_build_keeps_api_only_operation(tmp_path):
    client = TestClient(
        create_app(
            ManagementConfig(
                "postgresql://unused:unused@127.0.0.1:1/unused",
                frontend_assets_path=tmp_path / "not-built",
            )
        )
    )
    assert client.get("/health").status_code == 200
    assert client.get("/account").status_code == 404


def test_frontend_cannot_serve_files_outside_build_directory(tmp_path):
    build = tmp_path / "dist"
    build.mkdir()
    (build / "index.html").write_text("shell")
    secret = tmp_path / "private.txt"
    secret.write_text("private-outside-build")
    (build / "leaked.txt").symlink_to(secret)
    client = TestClient(
        create_app(
            ManagementConfig(
                "postgresql://unused:unused@127.0.0.1:1/unused",
                frontend_assets_path=build,
            )
        )
    )
    response = client.get("/leaked.txt")
    assert response.status_code == 404
    assert "private-outside-build" not in response.text


def test_frontend_index_symlink_outside_build_does_not_mount(tmp_path):
    build = tmp_path / "dist"
    build.mkdir()
    secret = tmp_path / "private.html"
    secret.write_text("private-outside-build")
    (build / "index.html").symlink_to(secret)
    client = TestClient(
        create_app(
            ManagementConfig(
                "postgresql://unused:unused@127.0.0.1:1/unused",
                frontend_assets_path=build,
            )
        )
    )
    assert client.get("/account").status_code == 404
