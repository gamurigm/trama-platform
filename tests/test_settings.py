import importlib.util
import os
from pathlib import Path


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
