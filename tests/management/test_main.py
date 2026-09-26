import logging

import pytest

from huginn.management import __main__ as entrypoint


def test_main_configures_logging_and_runs_local_development_server(monkeypatch):
    basic_config_calls = []
    run_calls = []

    class FakeApp:
        def run(self, **kwargs):
            run_calls.append(kwargs)

    monkeypatch.setattr(
        entrypoint.logging,
        "basicConfig",
        lambda **kwargs: basic_config_calls.append(kwargs),
    )
    monkeypatch.setattr(entrypoint, "create_app", lambda: FakeApp())

    entrypoint.main()

    assert basic_config_calls == [
        {
            "level": logging.INFO,
            "format": "%(asctime)s %(name)s %(levelname)s %(message)s",
        }
    ]
    assert run_calls == [
        {
            "host": "127.0.0.1",
            "port": 8000,
            "debug": False,
            "use_reloader": False,
        }
    ]


def test_main_does_not_start_server_when_configuration_is_missing(monkeypatch):
    def missing_config():
        raise RuntimeError("HUGINN_MANAGEMENT_DATABASE_URL is not set")

    monkeypatch.setattr(entrypoint, "create_app", missing_config)
    monkeypatch.setattr(entrypoint.logging, "basicConfig", lambda **kwargs: None)

    with pytest.raises(
        RuntimeError,
        match=r"^HUGINN_MANAGEMENT_DATABASE_URL is not set$",
    ):
        entrypoint.main()
