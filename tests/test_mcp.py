import asyncio
import importlib
import importlib.util
import sys

import httpx

TOOL_NAMES = {
    "trama_register_project",
    "trama_search_context",
    "trama_submit_task",
    "trama_record_result",
    "trama_capture_memory",
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
