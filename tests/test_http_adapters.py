import httpx
import pytest

from trama_platform.contracts import Evidence, MemoryCandidate, PromotionRequest
from trama_platform.http_adapters import SemanticaHttpAdapter, UtopiaHttpAdapter


def candidate() -> MemoryCandidate:
    return MemoryCandidate(
        candidate_id="candidate-1",
        project_id="demo",
        subject="tests",
        fact="tests pass",
        evidence=[Evidence(source="ci", locator="run/1")],
        confidence=1,
    )


def test_semantica_adapter_sends_contracts_and_authentication():
    requests = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if request.method == "POST":
            return httpx.Response(201, json={"candidate_id": "candidate-1"})
        return httpx.Response(200, json={"items": [candidate().model_dump(mode="json")]})

    adapter = SemanticaHttpAdapter(
        "https://semantica.test",
        token="secret",
        transport=httpx.MockTransport(handler),
    )

    assert adapter.put_candidate(candidate()) == "candidate-1"
    assert [item.candidate_id for item in adapter.search("default", "demo", "tests")] == [
        "candidate-1"
    ]
    assert requests[0].headers["authorization"] == "Bearer secret"
    assert requests[1].url.params["organization_id"] == "default"


def test_utopia_adapter_rejects_failed_promotion():
    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"code": "conflict", "message": "already exists"})

    request = PromotionRequest(
        promotion_id="promotion-1",
        candidate_id="candidate-1",
        project_id="demo",
        validations=["reviewed"],
        status="approved",
        approved_by="human",
    )

    adapter = UtopiaHttpAdapter(
        "https://utopia.test", transport=httpx.MockTransport(handler)
    )

    with pytest.raises(RuntimeError, match="already exists"):
        adapter.publish(request, candidate())
