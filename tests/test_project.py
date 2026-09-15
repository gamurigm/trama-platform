from pathlib import Path

import yaml

from trama_platform.project import load_project_manifest


def test_load_project_manifest():
    path = Path(__file__).parents[1] / "examples" / "generador-diccionario.project.yaml"
    manifest = load_project_manifest(path)

    assert manifest.project_id == "generador-diccionario-entidades"
    assert "oracle_audit" in manifest.capabilities
    assert manifest.policies.repositories_read_only is True


def test_hermes_template_uses_local_stdio_and_only_trama_tools():
    path = Path(__file__).parents[1] / "examples" / "hermes-config.yaml"
    config = yaml.safe_load(path.read_text(encoding="utf-8"))
    server = config["mcp_servers"]["trama"]

    assert server["command"] == "uv"
    assert server["args"][:4] == ["run", "--project", ".", "trama"]
    assert server["tools"]["include"] == [
        "trama_register_project",
        "trama_search_context",
        "trama_submit_task",
        "trama_record_result",
        "trama_capture_memory",
    ]
    assert server["tools"]["resources"] is False
    assert server["tools"]["prompts"] is False
    assert config["approvals"]["mode"] == "manual"
    assert "yolo" not in path.read_text(encoding="utf-8").casefold()


def test_native_hermes_template_connects_the_three_mcp_services():
    path = Path(__file__).parents[1] / "examples" / "hermes-native-config.yaml"
    raw = path.read_text(encoding="utf-8")
    config = yaml.safe_load(raw)

    assert config["model"]["default"] == "qwen3:8b"
    assert set(config["mcp_servers"]) == {"trama", "semantica", "utopia"}
    assert config["mcp_servers"]["trama"]["tools"]["resources"] is False
    assert config["mcp_servers"]["semantica"]["command"] == "semantica-mcp"
    assert config["mcp_servers"]["utopia"]["url"].endswith(
        "/api/v1/kbs/local/mcp"
    )
    assert "${UTOPIA_API_TOKEN}" in raw
    assert "real-token" not in raw
    assert "secret" not in raw.casefold()
    assert "yolo" not in raw.casefold()
