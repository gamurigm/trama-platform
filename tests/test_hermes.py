from pathlib import Path

from trama_platform.hermes import HermesAdapter


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
