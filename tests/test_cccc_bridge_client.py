import importlib
import importlib.util

import httpx
import pytest

from trama_platform.contracts import AgentResult, TaskEnvelope


def bridge_client_type():
    module_name = "trama_platform.cccc_bridge_client"
    assert importlib.util.find_spec(module_name) is not None, "bridge client module is missing"
    module = importlib.import_module(module_name)
    assert hasattr(module, "CcccBridgeCoordination"), "bridge client class is missing"
    return module.CcccBridgeCoordination


def make_task():
    return TaskEnvelope(
        task_id="bridge-task-1",
        project_id="integration-smoke",
        objective="Acknowledge receipt without using tools or changing files.",
        actor="agent-foreman",
        repository="local://integration-smoke",
        branch="experiment/smoke",
        worktree=".",
        read_only=True,
        acceptance_criteria=["Reply RECEIVED only."],
    )


def make_client(handler):
    client_type = bridge_client_type()
    return client_type(
        base_url="http://bridge.test",
        token="bridge-test-token",
        timeout_seconds=2,
        transport=httpx.MockTransport(handler),
    )


def test_bridge_client_submit_task_sends_bearer_and_returns_tracking_id():
    captured = {}

    def handler(request):
        captured["request"] = request
        return httpx.Response(200, json={"tracking_id": "cccc-track-1"})

    client = make_client(handler)
    task = make_task()

    tracking_id = client.submit_task(task)

    assert tracking_id == "cccc-track-1"
    request = captured["request"]
    assert request.url.path == "/v1/tasks"
    assert request.headers["authorization"] == "Bearer bridge-test-token"
    assert request.read() == task.model_dump_json().encode("utf-8")
    client.close()


def test_bridge_client_record_result_sends_agent_result():
    captured = {}

    def handler(request):
        captured["request"] = request
        return httpx.Response(204)

    client = make_client(handler)
    result = AgentResult(task_id="bridge-task-1", status="succeeded", summary="RECEIVED")

    client.record_result(result)

    request = captured["request"]
    assert request.url.path == "/v1/results"
    assert request.headers["authorization"] == "Bearer bridge-test-token"
    assert request.read() == result.model_dump_json().encode("utf-8")
    client.close()


@pytest.mark.parametrize(
    "handler",
    [
        lambda _: httpx.Response(503, json={"detail": "bridge unavailable"}),
        lambda _: (_ for _ in ()).throw(httpx.ConnectTimeout("timed out")),
    ],
)
def test_bridge_client_propagates_http_errors_and_timeouts(handler):
    client = make_client(handler)

    with pytest.raises(httpx.HTTPError):
        client.submit_task(make_task())

    client.close()
