import asyncio
import importlib
import importlib.util
import sys

import httpx

TOOL_NAMES = {
    "trama_register_project",
    "trama_register_requirement",
    "trama_register_phase",
    "trama_register_plan_proposal",
    "trama_approve_plan",
    "trama_search_context",
    "trama_submit_task",
    "trama_get_overview",
    "trama_get_task_timeline",
    "trama_get_phase_timeline",
    "trama_list_logs",
    "trama_record_log",
    "trama_record_result",
    "trama_capture_memory",
    "trama_get_task_result",
    "trama_get_memory_candidate",
    "trama_validate_memory_candidate",
    "trama_reject_memory_candidate",
}


def test_mcp_server_module_is_available():
    assert importlib.util.find_spec("trama_platform.mcp_server") is not None


def test_mcp_module_exposes_client_and_server_factory():
    module = importlib.import_module("trama_platform.mcp_server")

    assert hasattr(module, "TramaApiClient")
    assert hasattr(module, "create_mcp_server")


def test_api_client_posts_project_and_returns_api_json():
    module = importlib.import_module("trama_platform.mcp_server")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(201, json={"project_id": "demo", "status": "registered"})

    http_client = httpx.Client(transport=httpx.MockTransport(handler))
    api_client = module.TramaApiClient("http://trama.test", http_client=http_client)

    result = api_client.register_project(
        {
            "project_id": "demo",
            "organization_id": "org-a",
            "repository": "repo-a",
        }
    )

    assert result == {"project_id": "demo", "status": "registered"}
    assert seen[0].method == "POST"
    assert seen[0].url.path == "/v1/projects"


def test_api_client_adds_idempotency_key_when_submitting_to_go_gateway():
    module = importlib.import_module("trama_platform.mcp_server")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(202, json={"task_id": "task-1", "status": "accepted"})

    client = module.TramaApiClient(
        "http://trama.test",
        task_base_url="http://gateway.test",
        task_token="gateway-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    result = client.submit_task({"task_id": "task-1", "project_id": "demo"})

    assert result == {"task_id": "task-1", "status": "accepted"}
    assert seen[0].url.host == "gateway.test"
    assert seen[0].headers["idempotency-key"] == "task-1"
    assert seen[0].headers["authorization"] == "Bearer gateway-secret"


def test_api_client_reads_results_and_reviews_memory_in_a_namespace():
    module = importlib.import_module("trama_platform.mcp_server")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/result"):
            return httpx.Response(
                200,
                json={"task_id": "task-1", "status": "succeeded", "summary": "ok"},
            )
        return httpx.Response(200, json={"candidate_id": "candidate-1", "status": "validated"})

    client = module.TramaApiClient(
        "http://trama.test",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    assert client.get_task_result("task-1")["summary"] == "ok"
    assert client.validate_memory_candidate(
        "candidate-1", organization_id="org-a", project_id="demo", reviewer="human"
    )["status"] == "validated"
    assert seen[1].url.params["organization_id"] == "org-a"
    assert seen[1].url.params["project_id"] == "demo"


def test_api_client_routes_all_control_plane_calls_through_the_gateway_when_configured():
    module = importlib.import_module("trama_platform.mcp_server")
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    client = module.TramaApiClient(
        "http://private-control-plane.test",
        gateway_url="http://gateway.test",
        gateway_token="gateway-secret",
        http_client=httpx.Client(transport=httpx.MockTransport(handler)),
    )

    client.list_projects()

    assert seen[0].url.host == "gateway.test"
    assert seen[0].headers["authorization"] == "Bearer gateway-secret"


def test_mcp_server_exposes_only_the_scoped_trama_tools():
    module = importlib.import_module("trama_platform.mcp_server")

    class StubClient:
        def search_memory(self, request):
            return [{"candidate_id": "candidate-1", "project_id": request["project_id"]}]

    async def exercise() -> set[str]:
        from mcp import Client

        async with Client(module.create_mcp_server(StubClient())) as client:
            tools = await client.list_tools()
            return {tool.name for tool in tools.tools}

    assert asyncio.run(exercise()) == TOOL_NAMES


def test_cli_starts_mcp_with_the_configured_api_url(monkeypatch):
    cli = importlib.import_module("trama_platform.cli")
    started: list[str] = []
    monkeypatch.setattr(cli, "run_mcp", lambda api_url: started.append(api_url), raising=False)
    monkeypatch.setattr(
        sys,
        "argv",
        ["trama", "mcp", "--api-url", "http://127.0.0.1:8181"],
    )

    cli.main()

    assert started == ["http://127.0.0.1:8181"]


def test_cli_can_route_task_admission_from_mcp_to_the_go_gateway(monkeypatch):
    cli = importlib.import_module("trama_platform.cli")
    started: list[tuple[tuple[object, ...], dict[str, object]]] = []
    monkeypatch.setattr(
        cli,
        "run_mcp",
        lambda *args, **kwargs: started.append((args, kwargs)),
        raising=False,
    )
    monkeypatch.setenv("TRAMA_GATEWAY_TOKEN", "gateway-secret")
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "trama",
            "mcp",
            "--api-url",
            "http://127.0.0.1:8090",
            "--gateway-url",
            "http://127.0.0.1:8080",
        ],
    )

    cli.main()

    assert started == [
        (
            ("http://127.0.0.1:8090",),
            {"gateway_url": "http://127.0.0.1:8080", "gateway_token": "gateway-secret"},
        )
    ]
