from pathlib import Path

from trama_platform.hermes import HermesAdapter
from trama_platform.settings import TramaSettings


def test_hermes_profile_is_manual_and_scoped_to_trama(tmp_path: Path):
    config = HermesAdapter().render_config("http://127.0.0.1:8090")
    server = config["mcp_servers"]["trama"]

    assert config["approvals"]["mode"] == "manual"
    assert config["approvals"]["unattended_mode"] == "deny"
    assert server["command"] == "uv"
    assert server["tools"]["resources"] is False
    assert server["tools"]["prompts"] is False
    assert server["tools"]["include"] == HermesAdapter.TRAMA_TOOLS
    assert "secret" not in str(config).casefold()

    output = tmp_path / "hermes-config.yaml"
    HermesAdapter().write_config(output, "http://127.0.0.1:8090")
    assert "yolo" not in output.read_text(encoding="utf-8").casefold()


def test_hermes_check_reports_missing_executable(monkeypatch):
    monkeypatch.setattr("trama_platform.hermes.shutil.which", lambda _: None)

    result = HermesAdapter(executable="hermes").check()

    assert result == {"status": "missing", "executable": "hermes"}


def test_hermes_profile_configures_native_model_and_mcp_services():
    settings = TramaSettings(
        ollama_url="http://127.0.0.1:11434",
        ollama_model="qwen3:8b",
        colibri_url="http://127.0.0.1:8020",
        colibri_model="OLMoE-1B-7B-0125-Instruct",
        semantica_enabled=True,
        semantica_executable="semantica-mcp-local",
        utopia_mcp_url="http://127.0.0.1:1516/api/v1/kbs/local/mcp",
    )

    config = HermesAdapter().render_config(
        "http://127.0.0.1:8090",
        settings=settings,
        include_native_services=True,
    )

    assert config["model"] == {
        "default": "qwen3:8b",
        "provider": "custom",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "local",
    }
    providers = {entry["name"]: entry for entry in config["custom_providers"]}
    assert providers["ollama"] == {
        "name": "ollama",
        "base_url": "http://127.0.0.1:11434/v1",
        "api_key": "local",
        "models": ["qwen3:8b"],
    }
    assert providers["colibri"] == {
        "name": "colibri",
        "base_url": "http://127.0.0.1:8020/v1",
        "api_key": "local",
        "models": ["OLMoE-1B-7B-0125-Instruct"],
    }

    semantica = config["mcp_servers"]["semantica"]
    assert semantica == {
        "type": "stdio",
        "command": "semantica-mcp-local",
        "args": [],
    }
    utopia = config["mcp_servers"]["utopia"]
    assert utopia == {
        "type": "streamable-http",
        "url": "http://127.0.0.1:1516/api/v1/kbs/local/mcp",
        "headers": {"Authorization": "Bearer ${UTOPIA_API_TOKEN}"},
    }
    assert "real-token" not in str(config)
    assert "yolo" not in str(config).casefold()
