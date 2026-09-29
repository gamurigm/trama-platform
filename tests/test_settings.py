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


def test_settings_loads_only_required_memory_integration_vars(monkeypatch):
    monkeypatch.setenv("TRAMA_SEMANTICA_URL", "https://ignored.test")
    monkeypatch.setenv("TRAMA_SEMANTICA_VECTOR_BACKEND", "faiss")
    monkeypatch.setenv("TRAMA_SEMANTICA_VECTOR_DIMENSION", "1536")
    monkeypatch.setenv("TRAMA_EXTERNAL_TOKEN", "ignored-token")
    monkeypatch.setenv("TRAMA_SEMANTICA_KG_PATH", "artifacts/semantica-context")
    monkeypatch.setenv("TRAMA_UTOPIA_URL", "https://utopia.test")
    monkeypatch.setenv("TRAMA_UTOPIA_KB_ID", "kb-test")
    monkeypatch.setenv("TRAMA_UTOPIA_TOKEN", "token")

    settings = TramaSettings.from_env()

    assert settings.semantica_kg_path == "artifacts/semantica-context"
    assert settings.utopia_url == "https://utopia.test"
    assert settings.utopia_kb_id == "kb-test"
    assert settings.utopia_token == "token"
    assert not hasattr(settings, "semantica_url")
    assert not hasattr(settings, "external_token")


def test_cccc_bridge_backend_settings_validate_url_and_token(monkeypatch, tmp_path):
    from trama_platform.user_config import UserConfigStore

    monkeypatch.setenv("TRAMA_COORDINATION_BACKEND", "cccc-bridge")
    monkeypatch.setenv("TRAMA_CCCC_BRIDGE_URL", "http://host.docker.internal:8091")
    monkeypatch.setenv("TRAMA_CCCC_BRIDGE_TOKEN", "bridge-test-token")

    settings = TramaSettings.from_env(
        store=UserConfigStore(tmp_path / "config.json"),
        vault=type("Vault", (), {"get": lambda self, name: None})(),
    )

    assert settings.coordination_backend == "cccc-bridge"
    assert getattr(settings, "cccc_bridge_url", None) == "http://host.docker.internal:8091"
    assert getattr(settings, "cccc_bridge_token", None) == "bridge-test-token"


def test_cccc_bridge_actor_allowlist_is_parsed(monkeypatch):
    monkeypatch.setenv(
        "TRAMA_CCCC_ALLOWED_ACTORS", " agent-foreman, agent-backend-api ,, "
    )

    settings = TramaSettings.from_env()

    assert getattr(settings, "allowed_cccc_actors", None) == frozenset(
        {"agent-foreman", "agent-backend-api"}
    )


def test_cccc_bridge_settings_reject_url_credentials():
    import pytest

    with pytest.raises(ValueError, match="TRAMA_CCCC_BRIDGE_URL"):
        TramaSettings(cccc_bridge_url="http://user:password@host.docker.internal:8091")


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
        "TRAMA_TASK_LEASE_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)

    settings = TramaSettings.from_env()

    assert settings.queue_capacity == 100
    assert settings.max_concurrency == 4
    assert settings.dispatch_timeout_seconds == 900
    assert settings.task_lease_seconds == 60


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


def test_settings_uses_exact_olmoe_colibri_default(monkeypatch):
    monkeypatch.delenv("TRAMA_COLIBRI_MODEL", raising=False)

    settings = TramaSettings.from_env()

    assert settings.colibri_model == "OLMoE-1B-7B-0125-Instruct"


@pytest.mark.parametrize(
    "name,value",
    [
        ("TRAMA_OLLAMA_URL", "127.0.0.1:11434"),
        ("TRAMA_COLIBRI_URL", "ftp://127.0.0.1:8020"),
        ("TRAMA_UTOPIA_MCP_URL", "http://"),
        ("TRAMA_OLLAMA_URL", "http://user:password@127.0.0.1:11434"),
        ("TRAMA_COLIBRI_URL", "http://127.0.0.1:8020/path?token=secret"),
        ("TRAMA_UTOPIA_URL", "http://127.0.0.1:1516/path#fragment"),
    ],
)
def test_settings_rejects_non_http_service_urls(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        TramaSettings.from_env()


@pytest.mark.parametrize(
    "name",
    [
        "TRAMA_QUEUE_CAPACITY",
        "TRAMA_MAX_CONCURRENCY",
        "TRAMA_DISPATCH_TIMEOUT_SECONDS",
        "TRAMA_TASK_LEASE_SECONDS",
    ],
)
@pytest.mark.parametrize("value", ["0", "-1", "not-an-int"])
def test_queue_settings_reject_non_positive_values(monkeypatch, name, value):
    monkeypatch.setenv(name, value)

    with pytest.raises(ValueError, match=name):
        TramaSettings.from_env()


def test_settings_loads_task_lease_seconds(monkeypatch):
    monkeypatch.setenv("TRAMA_TASK_LEASE_SECONDS", "45")

    settings = TramaSettings.from_env()

    assert settings.task_lease_seconds == 45
