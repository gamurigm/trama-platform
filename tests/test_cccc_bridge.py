import importlib
import importlib.util
import json
import subprocess
from dataclasses import replace
from types import SimpleNamespace

from fastapi.testclient import TestClient

from trama_platform.contracts import AgentResult, TaskEnvelope
from trama_platform.settings import TramaSettings


class Coordination:
    def __init__(self):
        self.tasks = []
        self.results = []

    def submit_task(self, task):
        self.tasks.append(task)
        return "cccc-track-1"

    def record_result(self, result):
        self.results.append(result)


def settings(**changes):
    return replace(
        TramaSettings(),
        cccc_bridge_token="bridge-secret",
        cccc_allowed_actors="agent-foreman",
        cccc_result_recipient="agent-foreman",
        **changes,
    )


def task_payload(actor="agent-foreman"):
    return TaskEnvelope(
        task_id="bridge-task-1",
        project_id="integration-smoke",
        objective="Acknowledge receipt without using tools or changing files.",
        actor=actor,
        repository="local://integration-smoke",
        branch="experiment/smoke",
        worktree=".",
        read_only=True,
        acceptance_criteria=["Reply RECEIVED only."],
    ).model_dump(mode="json")


def bridge_app(config, cccc=None):
    module_name = "trama_platform.cccc_bridge"
    assert importlib.util.find_spec(module_name) is not None, "CCCC bridge module is missing"
    module = importlib.import_module(module_name)
    assert hasattr(module, "create_cccc_bridge_app"), "bridge app factory is missing"
    return module.create_cccc_bridge_app(config, cccc)


def auth_header():
    return {"Authorization": "Bearer bridge-secret"}


def test_task_endpoint_rejects_missing_or_invalid_token_before_cccc():
    cccc = Coordination()
    with TestClient(bridge_app(settings(), cccc)) as client:
        missing = client.post("/v1/tasks", json=task_payload())
        invalid = client.post(
            "/v1/tasks",
            json=task_payload(),
            headers={"Authorization": "Bearer wrong-token"},
        )

    assert missing.status_code == 401
    assert invalid.status_code == 401
    assert cccc.tasks == []


def test_task_endpoint_rejects_invalid_envelope_and_actor():
    cccc = Coordination()
    with TestClient(bridge_app(settings(), cccc)) as client:
        invalid_envelope = client.post(
            "/v1/tasks", json={"task_id": "bridge-task-1"}, headers=auth_header()
        )
        disallowed_actor = client.post(
            "/v1/tasks", json=task_payload("unlisted-actor"), headers=auth_header()
        )

    assert invalid_envelope.status_code == 422
    assert disallowed_actor.status_code == 403
    assert cccc.tasks == []


def test_task_endpoint_calls_submit_task_for_allowlisted_actor():
    cccc = Coordination()
    with TestClient(bridge_app(settings(), cccc)) as client:
        response = client.post("/v1/tasks", json=task_payload(), headers=auth_header())

    assert response.status_code == 202
    assert response.json() == {"tracking_id": "cccc-track-1"}
    assert [task.task_id for task in cccc.tasks] == ["bridge-task-1"]


def test_result_endpoint_uses_fixed_recipient(monkeypatch):
    completed = SimpleNamespace(stdout="")
    call = {}

    def run(*args, **kwargs):
        call["args"] = args
        call["kwargs"] = kwargs
        return completed

    monkeypatch.setattr("trama_platform.adapters.subprocess.run", run)
    result = AgentResult(task_id="bridge-task-1", status="succeeded", summary="RECEIVED")
    with TestClient(bridge_app(settings())) as client:
        response = client.post(
            "/v1/results",
            json=result.model_dump(mode="json"),
            headers=auth_header(),
        )

    assert response.status_code == 204
    command = call["args"][0]
    assert command[1] == "send"
    assert command[-2:] == ["--to", "agent-foreman"]
    assert json.loads(command[2])["task_id"] == "bridge-task-1"


def test_cccc_timeout_returns_sanitized_error(monkeypatch):
    def timeout(*args, **kwargs):
        raise subprocess.TimeoutExpired("cccc", timeout=30, output="private-body")

    monkeypatch.setattr("trama_platform.adapters.subprocess.run", timeout)
    with TestClient(bridge_app(settings())) as client:
        response = client.post("/v1/tasks", json=task_payload(), headers=auth_header())

    assert response.status_code == 504
    assert response.json() == {"detail": "CCCC request timed out"}
    assert "private-body" not in response.text
    assert "bridge-secret" not in response.text


def test_bridge_health_does_not_expose_configuration():
    with TestClient(bridge_app(settings())) as client:
        response = client.get("/healthz")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert "bridge-secret" not in response.text
