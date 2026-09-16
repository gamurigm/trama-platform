import pytest

from trama_platform.api import create_app
from trama_platform.settings import TramaSettings


def test_production_settings_require_a_postgres_url(monkeypatch):
    monkeypatch.setenv("TRAMA_ENV", "prod")
    monkeypatch.delenv("TRAMA_DATABASE_URL", raising=False)

    with pytest.raises(ValueError, match="TRAMA_DATABASE_URL"):
        TramaSettings.from_env()


def test_production_settings_select_postgres_backend(monkeypatch):
    monkeypatch.setenv("TRAMA_ENV", "prod")
    monkeypatch.setenv("TRAMA_DATABASE_URL", "postgresql://trama:secret@db/trama")

    settings = TramaSettings.from_env()

    assert settings.state_backend == "postgres"
    assert settings.database_url == "postgresql://trama:secret@db/trama"


def test_local_settings_keep_sqlite_by_default(monkeypatch):
    monkeypatch.setenv("TRAMA_ENV", "local")
    monkeypatch.delenv("TRAMA_DATABASE_URL", raising=False)

    settings = TramaSettings.from_env()

    assert settings.state_backend == "sqlite"


def test_build_state_store_uses_postgres_only_when_configured(monkeypatch):
    from trama_platform.cli import build_state_store
    from trama_platform.state_store import PostgresStateStore

    settings = TramaSettings(
        environment="prod",
        database_url="postgresql://trama:secret@db/trama",
    )

    monkeypatch.setattr(PostgresStateStore, "__init__", lambda self, url: None)
    store = build_state_store(settings)

    assert isinstance(store, PostgresStateStore)


def test_production_app_cannot_fall_back_to_in_memory_state():
    with pytest.raises(ValueError, match="state_store"):
        create_app(settings=TramaSettings(
            environment="prod",
            database_url="postgresql://trama:secret@db/trama",
        ))


def test_readiness_reports_an_unavailable_state_store():
    from fastapi.testclient import TestClient

    class BrokenStore:
        def ping(self):
            raise RuntimeError("database down")

    class Runtime:
        state_store = BrokenStore()

        def close(self):
            return None

    client = TestClient(create_app(Runtime()))

    assert client.get("/readyz").status_code == 503
