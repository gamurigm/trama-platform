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
    PlanProposal,
    ProjectManifest,
    ProjectPhase,
    PromotionRequest,
    Requirement,
    TaskEnvelope,
    TaskLog,
)


class TramaApiError(RuntimeError):
    """Error controlado al invocar la API HTTP de TRAMA."""


class TramaApiClient:
    """Cliente HTTP pequeño para el proceso MCP sin estado de negocio."""

    def __init__(
        self,
        base_url: str,
        *,
        task_base_url: str | None = None,
        task_token: str | None = None,
        http_client: httpx.Client | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.task_base_url = task_base_url.rstrip("/") if task_base_url else None
        self.task_token = task_token
        self.http_client = http_client or httpx.Client()

    def _post(
        self,
        path: str,
        payload: Mapping[str, Any],
        *,
        headers: Mapping[str, str] | None = None,
        base_url: str | None = None,
    ) -> Any:
        response = self.http_client.post(
            f"{base_url or self.base_url}{path}", json=dict(payload), headers=headers
        )
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

    def list_requirements(self, project_id: str | None = None) -> Any:
        suffix = "" if project_id is None else f"?project_id={project_id}"
        return self._get(f"/v1/requirements{suffix}")

    def register_requirement(self, requirement: Requirement | Mapping[str, Any]) -> Any:
        payload = (
            requirement.model_dump(mode="json")
            if isinstance(requirement, Requirement)
            else requirement
        )
        return self._post("/v1/requirements", payload)

    def list_phases(self, project_id: str | None = None) -> Any:
        suffix = "" if project_id is None else f"?project_id={project_id}"
        return self._get(f"/v1/phases{suffix}")

    def register_phase(self, phase: ProjectPhase | Mapping[str, Any]) -> Any:
        payload = phase.model_dump(mode="json") if isinstance(phase, ProjectPhase) else phase
        return self._post("/v1/phases", payload)

    def get_overview(self, project_id: str | None = None) -> Any:
        suffix = "" if project_id is None else f"?project_id={project_id}"
        return self._get(f"/v1/overview{suffix}")

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

    def get_task_timeline(self, task_id: str, limit: int = 100) -> Any:
        return self._get(f"/v1/tasks/{task_id}/timeline?limit={limit}")

    def get_phase_timeline(self, phase_id: str, limit: int = 100) -> Any:
        return self._get(f"/v1/phases/{phase_id}/timeline?limit={limit}")

    def list_logs(
        self,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        phase_id: str | None = None,
        requirement_id: str | None = None,
        level: str | None = None,
        limit: int = 100,
    ) -> Any:
        params = [f"{key}={value}" for key, value in (
            ("organization_id", organization_id),
            ("project_id", project_id),
            ("task_id", task_id),
            ("phase_id", phase_id),
            ("requirement_id", requirement_id),
            ("level", level),
        ) if value is not None]
        params.append(f"limit={limit}")
        return self._get(f"/v1/logs?{'&'.join(params)}")

    def register_plan_proposal(
        self, proposal: PlanProposal | Mapping[str, Any]
    ) -> Any:
        payload = (
            proposal.model_dump(mode="json")
            if isinstance(proposal, PlanProposal)
            else proposal
        )
        return self._post("/v1/plans", payload)

    def get_plan(self, proposal_id: str) -> Any:
        return self._get(f"/v1/plans/{proposal_id}")

    def approve_plan(self, proposal_id: str, approver: str) -> Any:
        return self._post(f"/v1/plans/{proposal_id}/approve", {"approver": approver})

    def record_task_log(self, log: TaskLog | Mapping[str, Any]) -> Any:
        payload = log.model_dump(mode="json") if isinstance(log, TaskLog) else log
        return self._post("/v1/logs", payload)

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
        task_id = payload.get("task_id")
        headers = {"Idempotency-Key": str(task_id)} if task_id else None
        if self.task_token:
            headers = {**(headers or {}), "Authorization": f"Bearer {self.task_token}"}
        return self._post(
            "/v1/tasks",
            payload,
            headers=headers,
            base_url=self.task_base_url,
        )

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
    def trama_register_requirement(
        requirement_id: str,
        project_id: str,
        title: str,
        description: str,
        acceptance_criteria: list[str],
        organization_id: str = "default",
        kind: Literal["feature", "change", "module", "refactor", "bugfix"] = "feature",
    ) -> dict[str, Any]:
        """Registra un requisito para que Hermes proponga su plan de fases."""

        return client.register_requirement(
            Requirement(
                requirement_id=requirement_id,
                organization_id=organization_id,
                project_id=project_id,
                title=title,
                description=description,
                kind=kind,
                acceptance_criteria=acceptance_criteria,
            )
        )

    @server.tool()
    def trama_register_phase(
        phase_id: str,
        requirement_id: str,
        project_id: str,
        name: str,
        sequence: int,
        acceptance_criteria: list[str],
        organization_id: str = "default",
        depends_on: list[str] | None = None,
    ) -> dict[str, Any]:
        """Registra una fase; dependencias ausentes permiten ejecución paralela."""

        return client.register_phase(
            ProjectPhase(
                phase_id=phase_id,
                requirement_id=requirement_id,
                organization_id=organization_id,
                project_id=project_id,
                name=name,
                sequence=sequence,
                depends_on=depends_on or [],
                acceptance_criteria=acceptance_criteria,
            )
        )

    @server.tool()
    def trama_register_plan_proposal(
        proposal_id: str,
        requirement_id: str,
        project_id: str,
        model_profile: str,
        summary: str,
        correlation_id: str,
        organization_id: str = "default",
        input_refs: list[str] | None = None,
        phase_ids: list[str] | None = None,
        task_ids: list[str] | None = None,
        version: int = 1,
    ) -> dict[str, Any]:
        """Registra una propuesta de la IA master sin aprobarla ni ejecutarla."""

        return client.register_plan_proposal(
            PlanProposal(
                proposal_id=proposal_id,
                requirement_id=requirement_id,
                organization_id=organization_id,
                project_id=project_id,
                model_profile=model_profile,
                input_refs=input_refs or [],
                phase_ids=phase_ids or [],
                task_ids=task_ids or [],
                summary=summary,
                version=version,
                correlation_id=correlation_id,
            )
        )

    @server.tool()
    def trama_approve_plan(proposal_id: str, approver: str) -> dict[str, Any]:
        """Aprueba explícitamente un plan; nunca se aprueba de forma implícita."""

        return client.approve_plan(proposal_id, approver)

    @server.tool()
    def trama_get_task_timeline(task_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Consulta eventos y logs de una tarea para observabilidad."""

        return client.get_task_timeline(task_id, limit)

    @server.tool()
    def trama_get_phase_timeline(phase_id: str, limit: int = 100) -> list[dict[str, Any]]:
        """Consulta el timeline agregado de una fase."""

        return client.get_phase_timeline(phase_id, limit)

    @server.tool()
    def trama_list_logs(
        project_id: str | None = None,
        organization_id: str | None = None,
        task_id: str | None = None,
        phase_id: str | None = None,
        requirement_id: str | None = None,
        level: Literal["debug", "info", "warning", "error"] | None = None,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        """Filtra logs saneados por proyecto, fase, tarea y nivel."""

        return client.list_logs(
            organization_id=organization_id,
            project_id=project_id,
            task_id=task_id,
            phase_id=phase_id,
            requirement_id=requirement_id,
            level=level,
            limit=limit,
        )

    @server.tool()
    def trama_record_log(
        project_id: str,
        message: str,
        correlation_id: str,
        organization_id: str = "default",
        level: Literal["debug", "info", "warning", "error"] = "info",
        requirement_id: str | None = None,
        phase_id: str | None = None,
        task_id: str | None = None,
        actor: str = "hermes",
        metadata: dict[str, Any] | None = None,
        duration_ms: int | None = None,
        sequence: int = 1,
    ) -> dict[str, Any]:
        """Registra un log de ejecución; TRAMA lo redacta antes de persistirlo."""

        return client.record_task_log(
            TaskLog(
                organization_id=organization_id,
                project_id=project_id,
                requirement_id=requirement_id,
                phase_id=phase_id,
                task_id=task_id,
                actor=actor,
                correlation_id=correlation_id,
                level=level,
                message=message,
                metadata=metadata or {},
                duration_ms=duration_ms,
                sequence=sequence,
            )
        )

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
        requirement_id: str | None = None,
        phase_id: str | None = None,
        source: Literal["manual", "requirement"] = "manual",
        state: Literal["planned", "accepted"] = "accepted",
        depends_on: list[str] | None = None,
    ) -> dict[str, Any]:
        """Envía una tarea al runtime y al coordinador configurado."""

        task = TaskEnvelope(
            task_id=task_id,
            parent_task_id=parent_task_id,
            requirement_id=requirement_id,
            phase_id=phase_id,
            source=source,
            state=state,
            depends_on=depends_on or [],
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
    def trama_get_overview(project_id: str | None = None) -> dict[str, Any]:
        """Consulta fases, cola CCCC, agentes y progreso para orientar a Hermes."""

        return client.get_overview(project_id)

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


def run_mcp(
    api_url: str,
    *,
    gateway_url: str | None = None,
    gateway_token: str | None = None,
) -> None:
    """Inicia el servidor MCP local sobre stdin/stdout."""

    create_mcp_server(
        TramaApiClient(
            api_url,
            task_base_url=gateway_url,
            task_token=gateway_token,
        )
    ).run(transport="stdio")
