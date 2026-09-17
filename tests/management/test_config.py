import pytest

from huginn.management import config


@pytest.fixture(autouse=True)
def disable_dotenv(monkeypatch):
    monkeypatch.setattr(config, "load_dotenv", lambda: False)


def test_load_config_reads_management_database_url_only(monkeypatch):
    management_url = "postgresql://manager:secret@management.test/huginn"
    monkeypatch.setenv("HUGINN_MANAGEMENT_DATABASE_URL", management_url)
    monkeypatch.setenv(
        "HUGINN_DATABASE_URL",
        "postgresql://elt:secret@elt.test/huginn",
    )

    loaded = config.load_config()

    assert loaded.database_url == management_url


@pytest.mark.parametrize("value", (None, "", " ", "\t", "\n"))
def test_load_config_rejects_missing_or_blank_management_url(monkeypatch, value):
    if value is None:
        monkeypatch.delenv("HUGINN_MANAGEMENT_DATABASE_URL", raising=False)
    else:
        monkeypatch.setenv("HUGINN_MANAGEMENT_DATABASE_URL", value)
    monkeypatch.setenv(
        "HUGINN_DATABASE_URL",
        "postgresql://elt:secret@elt.test/huginn",
    )

    with pytest.raises(
        RuntimeError,
        match=r"^HUGINN_MANAGEMENT_DATABASE_URL is not set$",
    ):
        config.load_config()


def test_management_config_hides_database_url_from_repr():
    database_url = "postgresql://manager:secret@management.test/huginn"

    rendered = repr(config.ManagementConfig(database_url=database_url))

    assert database_url not in rendered
    assert "secret" not in rendered
