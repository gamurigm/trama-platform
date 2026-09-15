"""Servidor MCP local de TRAMA."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Literal

import httpx
from mcp.server import MCPServer

from .contracts import (
    AgentResult,
    Evidence,
    MemoryCandidate,
    ProjectManifest,
    PromotionRequest,
    TaskEnvelope,
)


class TramaApiError(RuntimeError):
    """Error controlado al invocar la API HTTP de TRAMA."""


class TramaApiClient:
    """Cliente HTTP pequeño para el proceso MCP sin estado de negocio."""

    def __init__(self, base_url: str, *, http_client: httpx.Client | None = None) -> None:
        self.base_url = base_url.rstrip("/")
        self.http_client = http_client or httpx.Client()

    def _post(self, path: str, payload: Mapping[str, Any]) -> Any:
        response = self.http_client.post(f"{self.base_url}{path}", json=dict(payload))
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise TramaApiError(f"TRAMA API {response.status_code}: {detail}")
        return response.json()

    def _get(self, path: str) -> Any:
        response = self.http_client.get(f"{self.base_url}{path}")
        if response.is_error:
            try:
                detail = response.json().get("detail", response.text)
            except ValueError:
                detail = response.text
            raise TramaApiError(f"TRAMA API {response.status_code}: {detail}")
        return response.json()

    def get_status(self) -> Any:
        return self._get("/v1/status")

    def list_projects(self) -> Any:
        return self._get("/v1/projects")

    def get_project(self, project_id: str) -> Any:
        return self._get(f"/v1/projects/{project_id}")

    def list_tasks(self) -> Any:
        return self._get("/v1/tasks")

    def get_task(self, task_id: str) -> Any:
        return self._get(f"/v1/tasks/{task_id}")

    def cancel_task(self, task_id: str) -> Any:
        return self._post(f"/v1/tasks/{task_id}/cancel", {})

    def retry_task(self, task_id: str) -> Any:
        return self._post(f"/v1/tasks/{task_id}/retry", {})

    def list_agents(self) -> Any:
        return self._get("/v1/agents")

    def list_memory_candidates(self, organization_id: str, project_id: str) -> Any:
        return self._get(
            f"/v1/memory/candidates?organization_id={organization_id}&project_id={project_id}"
        )

    def list_events(self, limit: int = 100) -> Any:
        return self._get(f"/v1/events?limit={limit}")

    def register_project(self, manifest: ProjectManifest | Mapping[str, Any]) -> Any:
        payload = (
            manifest.model_dump(mode="json")
            if isinstance(manifest, ProjectManifest)
            else manifest
        )
        return self._post("/v1/projects", payload)

    def search_memory(self, request: Mapping[str, Any]) -> Any:
        return self._post("/v1/memory/search", request)

    def submit_task(self, task: TaskEnvelope | Mapping[str, Any]) -> Any:
        payload = task.model_dump(mode="json") if isinstance(task, TaskEnvelope) else task
        return self._post("/v1/tasks", payload)

    def record_result(self, result: AgentResult | Mapping[str, Any]) -> Any:
        payload = result.model_dump(mode="json") if isinstance(result, AgentResult) else result
        return self._post("/v1/results", payload)

    def capture_memory(self, candidate: MemoryCandidate | Mapping[str, Any]) -> Any:
        payload = (
            candidate.model_dump(mode="json")
            if isinstance(candidate, MemoryCandidate)
            else candidate
        )
        return self._post("/v1/memory/candidates", payload)

    def promote(self, request: PromotionRequest | Mapping[str, Any]) -> Any:
        payload = (
            request.model_dump(mode="json")
            if isinstance(request, PromotionRequest)
            else request
        )
        return self._post("/v1/knowledge/promotions", payload)


def create_mcp_server(client: TramaApiClient) -> MCPServer:
    """Construye el servidor MCP con el conjunto mínimo de herramientas TRAMA."""

    server = MCPServer("TRAMA", version="0.1.0")

    @server.tool()
    def trama_register_project(
        project_id: str,
        repository: str,
        organization_id: str = "default",
        default_branch: str = "main",
        capabilities: list[str] | None = None,
        commands: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        """Registra un proyecto sin aceptar credenciales."""

        manifest = ProjectManifest(
            project_id=project_id,
            organization_id=organization_id,
            repository=repository,
            default_branch=default_branch,
            capabilities=capabilities or [],
            commands=commands or {},
        )
        return client.register_project(manifest)

    @server.tool()
    def trama_search_context(
        organization_id: str,
        project_id: str,
        query: str,
    ) -> list[dict[str, Any]]:
        """Busca memoria visible dentro del namespace solicitado."""

        return client.search_memory(
            {"organization_id": organization_id, "project_id": project_id, "query": query}
        )

    @server.tool()
    def trama_submit_task(
        task_id: str,
        project_id: str,
        objective: str,
        actor: str,
        repository: str,
        branch: str,
        worktree: str,
        acceptance_criteria: list[str],
        organization_id: str = "default",
        parent_task_id: str | None = None,
        allowed_paths: list[str] | None = None,
        read_only: bool = False,
    ) -> dict[str, Any]:
        """Envía una tarea al runtime y al coordinador configurado."""

        task = TaskEnvelope(
            task_id=task_id,
            parent_task_id=parent_task_id,
            organization_id=organization_id,
            project_id=project_id,
            objective=objective,
            actor=actor,
            repository=repository,
            branch=branch,
            worktree=worktree,
            allowed_paths=allowed_paths or [],
            read_only=read_only,
            acceptance_criteria=acceptance_criteria,
        )
        return client.submit_task(task)

    @server.tool()
    def trama_record_result(
        task_id: str,
        status: Literal["succeeded", "partial", "failed", "blocked"],
        summary: str,
        files_changed: list[str] | None = None,
        commands: list[str] | None = None,
        warnings: list[str] | None = None,
        knowledge_candidates: list[str] | None = None,
    ) -> dict[str, Any]:
        """Registra el resultado verificable de una tarea existente."""

        result = AgentResult(
            task_id=task_id,
            status=status,
            summary=summary,
            files_changed=files_changed or [],
            commands=commands or [],
            warnings=warnings or [],
            knowledge_candidates=knowledge_candidates or [],
        )
        return client.record_result(result)

    @server.tool()
    def trama_capture_memory(
        candidate_id: str,
        project_id: str,
        subject: str,
        fact: str,
        evidence: list[dict[str, str]],
        confidence: float,
        organization_id: str = "default",
        visibility: Literal["private", "project", "shared"] = "project",
        sensitivity: Literal["public", "internal", "restricted", "secret"] = "internal",
    ) -> dict[str, Any]:
        """Captura un candidato con evidencia sin publicarlo como conocimiento canonico."""

        candidate = MemoryCandidate(
            candidate_id=candidate_id,
            organization_id=organization_id,
            project_id=project_id,
            subject=subject,
            fact=fact,
            evidence=[Evidence.model_validate(item) for item in evidence],
            confidence=confidence,
            visibility=visibility,
            sensitivity=sensitivity,
        )
        return client.capture_memory(candidate)

    return server


def run_mcp(api_url: str) -> None:
    """Inicia el servidor MCP local sobre stdin/stdout."""

    create_mcp_server(TramaApiClient(api_url)).run(transport="stdio")
