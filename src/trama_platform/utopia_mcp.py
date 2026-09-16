"""HTTP JSON-RPC MCP adapter for a Utopia knowledge base."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from .contracts import Evidence, MemoryCandidate, PromotionRequest
from .namespaces import can_promote
from .ports import CanonicalKnowledgePort, ContextMemoryPort


class UtopiaMcpError(RuntimeError):
    """Utopia MCP returned a transport or tool error."""


class UtopiaMcpAdapter(ContextMemoryPort, CanonicalKnowledgePort):
    """Use Utopia's documented per-knowledge-base MCP endpoint.

    Utopia's ``remember`` tool records a sentence and queues extracted facts
    for human review; it does not mean the graph was changed immediately.
    """

    def __init__(
        self,
        base_url: str,
        kb_id: str,
        *,
        token: str,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {token}"},
        )
        self.kb_id = kb_id
        self._request_id = 0
        self.candidates: dict[str, MemoryCandidate] = {}

    def _call_tool(self, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
        self._request_id += 1
        try:
            response = self.client.post(
                f"/api/v1/kbs/{self.kb_id}/mcp",
                json={
                    "jsonrpc": "2.0",
                    "id": self._request_id,
                    "method": "tools/call",
                    "params": {"name": name, "arguments": arguments},
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise UtopiaMcpError(str(exc)) from exc
        if "error" in payload:
            raise UtopiaMcpError(str(payload["error"]))
        result = payload.get("result") or {}
        if result.get("isError"):
            raise UtopiaMcpError(str(result))
        return result

    def put_candidate(self, candidate: MemoryCandidate) -> str:
        self.publish(
            PromotionRequest(
                promotion_id=f"utopia-{candidate.candidate_id}",
                candidate_id=candidate.candidate_id,
                organization_id=candidate.organization_id,
                project_id=candidate.project_id,
                validations=["trama-candidate"],
                approved_by="trama",
                status="approved",
            ),
            candidate.model_copy(update={"status": "validated"}),
        )
        return candidate.candidate_id

    def get_candidate(self, candidate_id: str) -> MemoryCandidate | None:
        return self.candidates.get(candidate_id)

    def search(
        self, organization_id: str, project_id: str, query: str, agent_id: str | None = None
    ) -> Sequence[MemoryCandidate]:
        result = self._call_tool("search_chunks", {"query": query})
        structured = result.get("structuredContent") or {}
        found: list[MemoryCandidate] = []
        for chunk in structured.get("chunks", []):
            candidate = MemoryCandidate(
                candidate_id=str(chunk["chunk_id"]),
                organization_id=organization_id,
                project_id=project_id,
                agent_id=agent_id,
                source="utopia",
                subject=str(chunk.get("filename") or "Utopia document"),
                fact=str(chunk.get("text") or ""),
                evidence=[
                    Evidence(
                        source="utopia",
                        locator=str(chunk.get("document_id") or chunk["chunk_id"]),
                    )
                ],
                confidence=1.0,
                status="validated",
            )
            self.candidates[candidate.candidate_id] = candidate
            found.append(candidate)
        return found

    def publish(self, request: PromotionRequest, candidate: MemoryCandidate) -> str:
        if not can_promote(request, candidate):
            raise PermissionError("La promocion no esta aprobada para el proyecto")
        if candidate.status != "validated":
            raise ValueError("Solo se puede registrar en Utopia un candidato validado")
        result = self._call_tool(
            "remember",
            {
                "text": f"{candidate.subject}: {candidate.fact}",
                "occurred_at": candidate.created_at.isoformat(),
            },
        )
        self.candidates[candidate.candidate_id] = candidate
        structured = result.get("structuredContent") or {}
        return str(structured.get("chunk_id") or candidate.candidate_id)

    def close(self) -> None:
        self.client.close()
