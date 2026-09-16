import importlib.util
import os
from pathlib import Path

import pytest

from trama_platform.settings import TramaSettings


def test_settings_module_is_available():
    assert importlib.util.find_spec("trama_platform.settings") is not None


def test_settings_loads_api_and_cccc_values_from_environment(monkeypatch):
    from trama_platform.settings import TramaSettings

    monkeypatch.setenv("TRAMA_API_HOST", "0.0.0.0")
    monkeypatch.setenv("TRAMA_API_PORT", "8181")
    monkeypatch.setenv("TRAMA_CCCC_TIMEOUT_SECONDS", "45")

    settings = TramaSettings.from_env()

    assert settings.api_host == "0.0.0.0"
    assert settings.api_port == 8181
    assert settings.cccc_timeout_seconds == 45


def test_settings_loads_optional_external_memory_urls(monkeypatch):
    monkeypatch.setenv("TRAMA_SEMANTICA_URL", "https://semantica.test")
    monkeypatch.setenv("TRAMA_UTOPIA_URL", "https://utopia.test")
    monkeypatch.setenv("TRAMA_EXTERNAL_TOKEN", "token")

    settings = TramaSettings.from_env()

    assert settings.semantica_url == "https://semantica.test"
    assert settings.utopia_url == "https://utopia.test"
    assert settings.external_token == "token"


def test_settings_loads_optional_colibri_profile(monkeypatch):
    monkeypatch.setenv("TRAMA_COLIBRI_URL", "http://127.0.0.1:8000")
    monkeypatch.setenv("TRAMA_COLIBRI_MODEL", "glm-local")

    settings = TramaSettings.from_env()

    assert settings.colibri_url == "http://127.0.0.1:8000"
    assert settings.colibri_model == "glm-local"


def test_settings_loads_python_task_consumer_nats_identity(monkeypatch):
    monkeypatch.setenv("TRAMA_NATS_URL", "nats://nats.test:4222")
    monkeypatch.setenv("TRAMA_NATS_STREAM", "TRAMA_EVENTS_TEST")
    monkeypatch.setenv("TRAMA_NATS_SUBJECT", "trama.task.admitted.v1")
    monkeypatch.setenv("TRAMA_NATS_DURABLE", "python-dispatch-test")

    settings = TramaSettings.from_env()

    assert settings.nats_url == "nats://nats.test:4222"
    assert settings.nats_stream == "TRAMA_EVENTS_TEST"
    assert settings.nats_subject == "trama.task.admitted.v1"
    assert settings.nats_durable == "python-dispatch-test"


def test_settings_loads_optional_go_gateway_task_route(monkeypatch):
    monkeypatch.setenv("TRAMA_GATEWAY_URL", "http://127.0.0.1:8080")
    monkeypatch.setenv("TRAMA_GATEWAY_TOKEN", "do-not-print")

    settings = TramaSettings.from_env()

    assert settings.gateway_url == "http://127.0.0.1:8080"
    assert settings.gateway_token == "do-not-print"


def test_settings_resolves_native_hermes_config_location(monkeypatch):
    from trama_platform.settings import TramaSettings

    monkeypatch.delenv("TRAMA_HERMES_CONFIG_PATH", raising=False)
    settings = TramaSettings.from_env()

    if os.name == "nt":
        expected = str(Path(os.environ["LOCALAPPDATA"]) / "hermes" / "config.yaml")
    else:
        expected = "~/.hermes/config.yaml"
    assert settings.hermes_config_path == expected


def test_queue_settings_have_safe_defaults(monkeypatch):
    for name in (
        "TRAMA_QUEUE_CAPACITY",
        "TRAMA_MAX_CONCURRENCY",
        "TRAMA_DISPATCH_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = TramaSettings.from_env()

    assert settings.queue_capacity == 100
    assert settings.max_concurrency == 4
    assert settings.dispatch_timeout_seconds == 900


@pytest.mark.parametrize(
    "name",
    ["TRAMA_QUEUE_CAPACITY", "TRAMA_MAX_CONCURRENCY", "TRAMA_DISPATCH_TIMEOUT_SECONDS"],
)
@pytest.mark.parametrize("value", ["0", "-1", "not-an-int"])
def test_queue_settings_reject_non_positive_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        TramaSettings.from_env()
