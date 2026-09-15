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


def test_settings_loads_native_service_values_from_environment(monkeypatch):
    monkeypatch.setenv("TRAMA_OLLAMA_URL", "http://127.0.0.1:11435")
    monkeypatch.setenv("TRAMA_OLLAMA_MODEL", "qwen3:4b")
    monkeypatch.setenv("TRAMA_COLIBRI_URL", "http://127.0.0.1:8021")
    monkeypatch.setenv("TRAMA_COLIBRI_MODEL", "olmoe-test")
    monkeypatch.setenv("TRAMA_COLIBRI_EXECUTABLE", "coli-test")
    monkeypatch.setenv("TRAMA_SEMANTICA_ENABLED", "true")
    monkeypatch.setenv("TRAMA_SEMANTICA_EXECUTABLE", "semantica-test")
    monkeypatch.setenv("TRAMA_UTOPIA_URL", "https://127.0.0.1:1517")
    monkeypatch.setenv(
        "TRAMA_UTOPIA_MCP_URL",
        "https://127.0.0.1:1517/api/v1/kbs/local/mcp",
    )

    settings = TramaSettings.from_env()

    assert settings.ollama_url == "http://127.0.0.1:11435"
    assert settings.ollama_model == "qwen3:4b"
    assert settings.colibri_url == "http://127.0.0.1:8021"
    assert settings.colibri_model == "olmoe-test"
    assert settings.colibri_executable == "coli-test"
    assert settings.semantica_enabled is True
    assert settings.semantica_executable == "semantica-test"
    assert settings.utopia_url == "https://127.0.0.1:1517"
    assert settings.utopia_mcp_url == "https://127.0.0.1:1517/api/v1/kbs/local/mcp"


@pytest.mark.parametrize(
    "name,value",
    [
        ("TRAMA_OLLAMA_URL", "127.0.0.1:11434"),
        ("TRAMA_COLIBRI_URL", "ftp://127.0.0.1:8020"),
        ("TRAMA_UTOPIA_MCP_URL", "http://"),
    ],
)
def test_settings_rejects_non_http_service_urls(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        TramaSettings.from_env()


@pytest.mark.parametrize(
    "name",
    ["TRAMA_QUEUE_CAPACITY", "TRAMA_MAX_CONCURRENCY", "TRAMA_DISPATCH_TIMEOUT_SECONDS"],
)
@pytest.mark.parametrize("value", ["0", "-1", "not-an-int"])
def test_queue_settings_reject_non_positive_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        TramaSettings.from_env()
