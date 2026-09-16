from __future__ import annotations

import json

import httpx

from trama_platform.colibri import ColibriModelGateway
from trama_platform.contracts import ModelRequest


def test_colibri_gateway_resolves_prompt_and_stores_a_successful_completion():
    requests: list[httpx.Request] = []
    stored: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(
            200,
            json={
                "model": "glm-local",
                "choices": [{"message": {"content": "Use the focused test."}}],
            },
        )

    gateway = ColibriModelGateway(
        "http://colibri.test",
        model_id="glm-local",
        api_key="local-secret",
        prompt_resolver=lambda _: [{"role": "user", "content": "Plan the fix"}],
        result_sink=lambda _, content: stored.append(content) or "memory://result-1",
        transport=httpx.MockTransport(handler),
    )
    request = ModelRequest(
        request_id="request-1",
        project_id="demo",
        agent_id="hermes",
        model_profile="local",
        purpose="plan",
        input_reference="memory://prompt-1",
    )

    result = gateway.complete(request)

    assert result.status == "succeeded"
    assert result.provider == "colibri"
    assert result.model == "glm-local"
    assert result.output_reference == "memory://result-1"
    assert stored == ["Use the focused test."]
    assert requests[0].url.path == "/v1/chat/completions"
    assert requests[0].headers["authorization"] == "Bearer local-secret"
    assert json.loads(requests[0].content) == {
        "model": "glm-local",
        "messages": [{"role": "user", "content": "Plan the fix"}],
        "stream": False,
    }
