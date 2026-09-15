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


@pytest.mark.parametrize(
    "name",
    ["TRAMA_QUEUE_CAPACITY", "TRAMA_MAX_CONCURRENCY", "TRAMA_DISPATCH_TIMEOUT_SECONDS"],
)
@pytest.mark.parametrize("value", ["0", "-1", "not-an-int"])
def test_queue_settings_reject_non_positive_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        TramaSettings.from_env()
