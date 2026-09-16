"""Adaptadores HTTP opcionales para memoria contextual y conocimiento canónico."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import httpx

from .contracts import MemoryCandidate, PromotionRequest
from .ports import CanonicalKnowledgePort, ContextMemoryPort


class ExternalServiceError(RuntimeError):
    """El servicio externo rechazó o no pudo procesar una operación."""


class _HttpAdapter:
    def __init__(
        self,
        base_url: str,
        *,
        token: str | None = None,
        timeout: float = 10.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {token}"} if token else None,
        )

    def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = self.client.request(method, path, **kwargs)
        except httpx.HTTPError as exc:
            raise ExternalServiceError(str(exc)) from exc
        if response.is_error:
            try:
                detail = response.json().get("message", response.text)
            except ValueError:
                detail = response.text
            raise ExternalServiceError(str(detail))
        if not response.content:
            return {}
        return response.json()

    def close(self) -> None:
        self.client.close()


class SemanticaHttpAdapter(_HttpAdapter, ContextMemoryPort):
    def put_candidate(self, candidate: MemoryCandidate) -> str:
        payload = self._request(
            "POST", "/v1/memory/candidates", json=candidate.model_dump(mode="json")
        )
        return str(payload.get("candidate_id", candidate.candidate_id))

    def get_candidate(self, candidate_id: str) -> MemoryCandidate | None:
        try:
            payload = self._request("GET", f"/v1/memory/candidates/{candidate_id}")
        except ExternalServiceError as exc:
            if "404" in str(exc):
                return None
            raise
        return MemoryCandidate.model_validate(payload)

    def search(
        self, organization_id: str, project_id: str, query: str, agent_id: str | None = None
    ) -> Sequence[MemoryCandidate]:
        payload = self._request(
            "GET",
            "/v1/memory/candidates",
            params={
                "organization_id": organization_id,
                "project_id": project_id,
                "q": query,
            },
        )
        return [
            item
            for item in (MemoryCandidate.model_validate(item) for item in payload.get("items", []))
            if item.organization_id == organization_id
            and item.project_id == project_id
            and (item.visibility != "private" or item.agent_id == agent_id)
        ]


class UtopiaHttpAdapter(_HttpAdapter, CanonicalKnowledgePort):
    def publish(self, request: PromotionRequest, candidate: MemoryCandidate) -> str:
        payload = self._request(
            "POST",
            "/v1/knowledge/promotions",
            json={
                "request": request.model_dump(mode="json"),
                "candidate": candidate.model_dump(mode="json"),
            },
        )
        return str(payload.get("promotion_id", request.promotion_id))
