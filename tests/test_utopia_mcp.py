import json

import httpx

from trama_platform.contracts import Evidence, MemoryCandidate, PromotionRequest
from trama_platform.utopia_mcp import UtopiaMcpAdapter


def candidate():
    return MemoryCandidate(
        candidate_id="candidate-1", organization_id="org-a", project_id="demo",
        agent_id="specialist-db", task_id="task-1", source="semantica",
        subject="audit", fact="Trigger writes an audit row",
        evidence=[Evidence(source="repo", locator="src/a.sql")], confidence=0.9,
        status="validated",
    )


def test_utopia_adapter_uses_documented_mcp_endpoint_and_tools():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        body = json.loads(request.content)
        if body["params"]["name"] == "search_chunks":
            result = {"structuredContent": {"kb_id": "kb-1", "chunks": [{
                "chunk_id": "chunk-1", "document_id": "doc-1", "filename": "audit.md",
                "text": "Trigger writes an audit row",
            }]}}
        else:
            result = {"content": [{"type": "text", "text": "recorded"}]}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    adapter = UtopiaMcpAdapter(
        "https://utopia.test", "kb-1", token="utp_pat_test", transport=httpx.MockTransport(handler)
    )
    request = PromotionRequest(
        promotion_id="promotion-1", candidate_id="candidate-1", organization_id="org-a",
        project_id="demo", validations=["human-review"], approved_by="human", status="approved",
    )

    assert adapter.publish(request, candidate()) == "candidate-1"
    result = adapter.search("org-a", "demo", "audit")
    assert result[0].fact == "Trigger writes an audit row"
    assert str(requests[0].url) == "https://utopia.test/api/v1/kbs/kb-1/mcp"
    assert requests[0].headers["authorization"] == "Bearer utp_pat_test"
