import importlib
import json
import sys
from types import SimpleNamespace

import httpx
import pytest


def test_cli_status_emits_machine_readable_json(monkeypatch, capsys):
    cli = importlib.import_module("trama_platform.cli")

    class FakeClient:
        def __init__(self, base_url):
            assert base_url == "http://trama.test"

        def get_status(self):
            return {"service": "trama", "status": "ready", "projects": 1}

    monkeypatch.setattr(cli, "TramaApiClient", FakeClient)
    monkeypatch.setattr(
        sys, "argv", ["trama", "status", "--api-url", "http://trama.test", "--json"]
    )

    cli.main()

    assert json.loads(capsys.readouterr().out) == {
        "service": "trama",
        "status": "ready",
        "projects": 1,
    }


def test_cli_doctor_emits_nonzero_json_when_api_is_unavailable(monkeypatch, capsys):
    cli = importlib.import_module("trama_platform.cli")

    class BrokenClient:
        def __init__(self, base_url):
            pass

        def get_status(self):
            raise cli.TramaApiError("API unavailable")

    monkeypatch.setattr(cli, "TramaApiClient", BrokenClient)
    monkeypatch.setattr(
        sys, "argv", ["trama", "doctor", "--api-url", "http://trama.test", "--json"]
    )

    try:
        cli.main()
    except SystemExit as exc:
        assert exc.code == 1
    else:
        raise AssertionError("doctor debe salir con codigo 1")

    assert json.loads(capsys.readouterr().out) == {
        "status": "error",
        "code": "api_unavailable",
        "message": "API unavailable",
    }


def test_cli_doctor_normalizes_connection_errors(monkeypatch, capsys):
    cli = importlib.import_module("trama_platform.cli")

    class BrokenClient:
        def __init__(self, base_url):
            pass

        def get_status(self):
            raise httpx.ConnectError("connection refused")

    monkeypatch.setattr(cli, "TramaApiClient", BrokenClient)
    monkeypatch.setattr(
        sys, "argv", ["trama", "doctor", "--api-url", "http://trama.test", "--json"]
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main()

    assert exc_info.value.code == 1
    assert json.loads(capsys.readouterr().out) == {
        "status": "error",
        "code": "api_unavailable",
        "message": "connection refused",
    }


def test_coordination_factory_builds_cccc_adapter():
    cli = importlib.import_module("trama_platform.cli")
    settings = cli.TramaSettings(
        coordination_backend="cccc",
        cccc_executable="cccc-test",
        cccc_timeout_seconds=17,
    )

    adapter = cli.build_coordination(settings)

    assert isinstance(adapter, cli.CcccCliAdapter)
    assert adapter.executable == "cccc-test"
    assert adapter.timeout_seconds == 17


def test_cli_hermes_check_emits_adapter_status(monkeypatch, capsys):
    cli = importlib.import_module("trama_platform.cli")

    class FakeHermes:
        def __init__(self, executable, **kwargs):
            assert executable == "hermes"

        def check(self):
            return {"status": "ready", "executable": "hermes", "version": "1.0"}

    monkeypatch.setattr(cli, "HermesAdapter", FakeHermes)
    monkeypatch.setattr(sys, "argv", ["trama", "hermes", "check", "--json"])

    cli.main()

    assert json.loads(capsys.readouterr().out)["status"] == "ready"


def test_cli_hermes_configure_writes_profile(monkeypatch, tmp_path, capsys):
    cli = importlib.import_module("trama_platform.cli")
    written: list[tuple[str, str]] = []

    class FakeHermes:
        def __init__(self, executable, **kwargs):
            pass

        def write_config(self, path, api_url):
            written.append((str(path), api_url))
            return path

    monkeypatch.setattr(cli, "HermesAdapter", FakeHermes)
    output = tmp_path / "config.yaml"
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "trama",
            "hermes",
            "configure",
            "--path",
            str(output),
            "--api-url",
            "http://trama.test",
            "--json",
        ],
    )

    cli.main()

    assert written == [(str(output), "http://trama.test")]
    assert json.loads(capsys.readouterr().out) == {
        "status": "written",
        "path": str(output),
    }


def test_cli_up_and_down_delegate_to_gateway_supervisor(monkeypatch, capsys):
    cli = importlib.import_module("trama_platform.cli")
    operations = []

    class FakeSupervisor:
        def __init__(self, **kwargs):
            operations.append(("init", kwargs))

        def start(self):
            operations.append(("start",))
            return {"status": "started", "pid": 1234}

        def stop(self):
            operations.append(("stop",))
            return {"status": "stopped", "pid": 1234}

    monkeypatch.setattr(cli, "GatewaySupervisor", FakeSupervisor)
    monkeypatch.setattr(sys, "argv", ["trama", "up", "--json"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["status"] == "started"

    monkeypatch.setattr(sys, "argv", ["trama", "down", "--json"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["status"] == "stopped"
    assert [item[0] for item in operations] == ["init", "start", "init", "stop"]


def test_cli_agent_and_knowledge_commands_use_scoped_api_queries(monkeypatch, capsys):
    cli = importlib.import_module("trama_platform.cli")

    class FakeClient:
        def __init__(self, base_url):
            pass

        def list_agents(self):
            return [{"agent_id": "codex", "tasks": 1, "projects": ["demo"]}]

        def list_memory_candidates(self, organization_id, project_id):
            assert (organization_id, project_id) == ("org-a", "demo")
            return [{"candidate_id": "candidate-1"}]

    monkeypatch.setattr(cli, "TramaApiClient", FakeClient)
    monkeypatch.setattr(sys, "argv", ["trama", "agent", "list", "--json"])
    cli.main()
    assert json.loads(capsys.readouterr().out)[0]["agent_id"] == "codex"

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "trama",
            "knowledge",
            "candidates",
            "--organization",
            "org-a",
            "--project",
            "demo",
            "--json",
        ],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)[0]["candidate_id"] == "candidate-1"


def test_cli_mcp_model_and_config_commands_are_explicit(monkeypatch, capsys):
    cli = importlib.import_module("trama_platform.cli")

    class FakeClient:
        def __init__(self, base_url):
            pass

        def get_status(self):
            return {"status": "ready"}

    monkeypatch.setattr(cli, "TramaApiClient", FakeClient)
    monkeypatch.setattr(sys, "argv", ["trama", "mcp", "check", "--json"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["transport"] == "stdio"

    monkeypatch.setattr(sys, "argv", ["trama", "model", "list", "--json"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["status"] == "not_configured"

    monkeypatch.setattr(sys, "argv", ["trama", "config", "get", "--json"])
    cli.main()
    config = json.loads(capsys.readouterr().out)
    assert config["api_host"] == "127.0.0.1"
    assert config["queue_capacity"] == 100
    assert config["max_concurrency"] == 4
    assert config["dispatch_timeout_seconds"] == 900


def test_cli_api_passes_queue_settings_to_app(monkeypatch, tmp_path):
    cli = importlib.import_module("trama_platform.cli")
    captured = {}

    monkeypatch.setenv("TRAMA_QUEUE_CAPACITY", "7")
    monkeypatch.setenv("TRAMA_MAX_CONCURRENCY", "3")
    monkeypatch.setenv("TRAMA_DISPATCH_TIMEOUT_SECONDS", "21")
    monkeypatch.setenv("TRAMA_STATE_DIR", str(tmp_path))

    def fake_create_app(**kwargs):
        captured.update(kwargs)
        return object()

    def fake_run(app, **kwargs):
        captured["uvicorn"] = kwargs

    monkeypatch.setattr(cli, "create_app", fake_create_app)
    monkeypatch.setitem(sys.modules, "uvicorn", SimpleNamespace(run=fake_run))
    monkeypatch.setattr(sys, "argv", ["trama", "api"])

    cli.main()

    assert captured["settings"].queue_capacity == 7
    assert captured["settings"].max_concurrency == 3
    assert captured["settings"].dispatch_timeout_seconds == 21
    assert captured["uvicorn"] == {"host": "127.0.0.1", "port": 8090}


def test_cli_can_inspect_a_project_and_submit_a_task_file(monkeypatch, tmp_path, capsys):
    cli = importlib.import_module("trama_platform.cli")
    calls = []

    class FakeClient:
        def __init__(self, base_url):
            pass

        def get_project(self, project_id):
            calls.append(("project", project_id))
            return {"project_id": project_id}

        def submit_task(self, task):
            calls.append(("task", task.task_id))
            return {"task_id": task.task_id, "status": "accepted"}

    monkeypatch.setattr(cli, "TramaApiClient", FakeClient)
    monkeypatch.setattr(sys, "argv", ["trama", "project", "inspect", "demo", "--json"])
    cli.main()
    assert json.loads(capsys.readouterr().out)["project_id"] == "demo"

    task_file = tmp_path / "task.json"
    task_file.write_text(
        json.dumps(
            {
                "task_id": "task-1",
                "project_id": "demo",
                "objective": "Run tests",
                "actor": "codex",
                "repository": "repo-a",
                "branch": "main",
                "worktree": "C:/work/demo",
                "acceptance_criteria": ["tests pass"],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(
        sys,
        "argv",
        ["trama", "task", "submit", "--file", str(task_file), "--json"],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["task_id"] == "task-1"
    assert calls == [("project", "demo"), ("task", "task-1")]


def test_cli_requires_explicit_confirmation_for_knowledge_promotion(monkeypatch, tmp_path, capsys):
    cli = importlib.import_module("trama_platform.cli")

    class FakeClient:
        def __init__(self, base_url):
            pass

        def promote(self, request):
            return {"promotion_id": request.promotion_id, "status": "published"}

    request_file = tmp_path / "promotion.json"
    request_file.write_text(
        json.dumps(
            {
                "promotion_id": "promotion-1",
                "candidate_id": "candidate-1",
                "project_id": "demo",
                "validations": ["review"],
                "approved_by": "operator",
                "status": "approved",
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(cli, "TramaApiClient", FakeClient)
    monkeypatch.setattr(
        sys,
        "argv",
        ["trama", "knowledge", "promote", "--file", str(request_file), "--json"],
    )

    with pytest.raises(SystemExit, match="confirm"):
        cli.main()
    capsys.readouterr()

    monkeypatch.setattr(
        sys,
        "argv",
        [
            "trama",
            "knowledge",
            "promote",
            "--file",
            str(request_file),
            "--confirm",
            "--json",
        ],
    )
    cli.main()
    assert json.loads(capsys.readouterr().out)["status"] == "published"
