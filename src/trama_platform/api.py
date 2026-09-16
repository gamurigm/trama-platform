"""API HTTP mínima para integrar proyectos sin compartir sus dependencias."""

from __future__ import annotations

from contextlib import asynccontextmanager
from hmac import compare_digest

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import JSONResponse

from .context import ContextError, RequestContext
from .contracts import (
    AgentResult,
    LogLevel,
    MemoryCandidate,
    MemorySearchRequest,
    OperationEvent,
    PlanProposal,
    ProjectManifest,
    ProjectPhase,
    PromotionRequest,
    Requirement,
    TaskEnvelope,
    TaskLog,
    TimelineEntry,
)
from .ports import CanonicalKnowledgePort, ContextMemoryPort, CoordinationPort, StateStorePort
from .queueing import QueueCapacityError
from .runtime import TramaRuntime
from .settings import TramaSettings


def create_app(
    runtime: TramaRuntime | None = None,
    *,
    coordination: CoordinationPort | None = None,
    context_memory: ContextMemoryPort | None = None,
    canonical_knowledge: CanonicalKnowledgePort | None = None,
    state_store: StateStorePort | None = None,
    settings: TramaSettings | None = None,
) -> FastAPI:
    if settings and settings.is_production and runtime is None and state_store is None:
        raise ValueError("state_store es obligatorio en produccion")
    runtime_instance = runtime or TramaRuntime(
        coordination=coordination,
        context_memory=context_memory,
        canonical_knowledge=canonical_knowledge,
        state_store=state_store,
        queue_capacity=settings.queue_capacity if settings else 100,
        max_concurrency=settings.max_concurrency if settings else 4,
        dispatch_timeout_seconds=(
            settings.dispatch_timeout_seconds if settings else 900
        ),
        lease_seconds=settings.task_lease_seconds if settings else 60,
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        runtime_instance.close()

    app = FastAPI(title="TRAMA", version="0.1.0", lifespan=lifespan)
    app.state.runtime = runtime_instance
    configured_store = state_store or getattr(runtime_instance, "state_store", None)

    tenant_context_required = bool(
        settings and (settings.is_production or settings.require_tenant_context)
    )

    def request_context(request: Request) -> RequestContext:
        return request.state.trama_context

    def ensure_namespace(request: Request, value: object) -> object:
        if not tenant_context_required:
            return value
        context = request_context(request)
        organization_id = getattr(value, "organization_id", None)
        project_id = getattr(value, "project_id", None)
        if organization_id not in {"default", context.organization_id}:
            raise HTTPException(
                status_code=403,
                detail="La organizacion del request no esta autorizada",
            )
        if context.project_id and project_id != context.project_id:
            raise HTTPException(
                status_code=403,
                detail="El proyecto del request no esta autorizado",
            )
        if hasattr(value, "organization_id"):
            return value.model_copy(update={"organization_id": context.organization_id})
        return value

    def ensure_path_namespace(request: Request, project_id: str | None = None) -> None:
        if not tenant_context_required:
            return
        context = request_context(request)
        if context.project_id and project_id and context.project_id != project_id:
            raise HTTPException(
                status_code=403,
                detail="El proyecto del request no esta autorizado",
            )

    def visible_items(request: Request, items: list[object]) -> list[object]:
        if not tenant_context_required:
            return items
        context = request_context(request)
        return [
            item
            for item in items
            if getattr(item, "organization_id", None) == context.organization_id
            and (
                context.project_id is None
                or getattr(item, "project_id", None) == context.project_id
            )
        ]

    def visible_overview(request: Request, overview: dict[str, object]) -> dict[str, object]:
        if not tenant_context_required:
            return overview
        context = request_context(request)
        requirements = [
            item
            for item in overview.get("requirements", [])
            if item.get("organization_id") == context.organization_id
            and (context.project_id is None or item.get("project_id") == context.project_id)
        ]
        phases = [
            item
            for item in overview.get("phases", [])
            if item.get("organization_id") == context.organization_id
            and (context.project_id is None or item.get("project_id") == context.project_id)
        ]
        queue = [
            item
            for item in overview.get("queue", [])
            if item.get("organization_id") == context.organization_id
            and (context.project_id is None or item.get("project_id") == context.project_id)
        ]
        visible_phase_ids = {item.get("phase_id") for item in phases}
        visible_task_ids = {item.get("task_id") for item in queue}
        visible_agent_ids = {item.get("actor") for item in queue}
        activity = [
            item
            for item in overview.get("latest_activity", [])
            if item.get("organization_id") == context.organization_id
            and (context.project_id is None or item.get("project_id") == context.project_id)
        ]
        return {
            **overview,
            "requirements": requirements,
            "phases": phases,
            "queue": queue,
            "agents": [
                item
                for item in overview.get("agents", [])
                if item.get("agent_id") in visible_agent_ids
            ],
            "parallel_groups": [
                {
                    **group,
                    "phase_ids": [
                        phase_id
                        for phase_id in group.get("phase_ids", [])
                        if phase_id in visible_phase_ids
                    ],
                }
                for group in overview.get("parallel_groups", [])
                if any(phase_id in visible_phase_ids for phase_id in group.get("phase_ids", []))
            ],
            "pending_approval": [
                item
                for item in overview.get("pending_approval", [])
                if item in visible_phase_ids or item in visible_task_ids
            ],
            "blocked_dependencies": [
                item
                for item in overview.get("blocked_dependencies", [])
                if item in visible_phase_ids or item in visible_task_ids
            ],
            "latest_activity": activity,
        }

    @app.middleware("http")
    async def require_api_token(request: Request, call_next):
        expected = settings.api_token if settings else None
        probe_path = request.url.path in {"/health", "/livez", "/readyz"}
        if expected and not probe_path:
            authorization = request.headers.get("authorization", "")
            scheme, _, supplied = authorization.partition(" ")
            if scheme.casefold() != "bearer" or not compare_digest(supplied, expected):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Se requiere un token Bearer válido"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
        internal_expected = settings.internal_service_token if settings else None
        if internal_expected and not probe_path:
            supplied_internal = request.headers.get("x-trama-internal-token", "")
            if not compare_digest(supplied_internal, internal_expected):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Se requiere identidad interna del gateway"},
                )
        try:
            request.state.trama_context = RequestContext.from_headers(
                request.headers,
                default_organization=settings.organization_id if settings else "default",
                required=tenant_context_required and not probe_path,
            )
        except ContextError as exc:
            return JSONResponse(status_code=400, content={"detail": str(exc)})
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "trama"}

    @app.get("/livez")
    def livez() -> dict[str, str]:
        return {"status": "alive", "service": "trama"}

    @app.get("/readyz")
    def readyz() -> dict[str, str]:
        if configured_store is not None and hasattr(configured_store, "ping"):
            try:
                configured_store.ping()
            except Exception as exc:
                raise HTTPException(status_code=503, detail="State store is unavailable") from exc
        return {"status": "ready", "service": "trama"}

    @app.get("/v1/status")
    def status() -> dict[str, object]:
        return app.state.runtime.status()

    @app.get("/v1/projects", response_model=list[ProjectManifest])
    def list_projects(request: Request) -> list[ProjectManifest]:
        return visible_items(request, app.state.runtime.list_projects())

    @app.get("/v1/projects/{project_id}", response_model=ProjectManifest)
    def get_project(request: Request, project_id: str) -> ProjectManifest:
        ensure_path_namespace(request, project_id)
        try:
            project = app.state.runtime.get_project(project_id)
            return ensure_namespace(request, project)  # type: ignore[return-value]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/projects", response_model=ProjectManifest, status_code=201)
    def register_project(request: Request, manifest: ProjectManifest) -> ProjectManifest:
        manifest = ensure_namespace(request, manifest)  # type: ignore[assignment]
        try:
            return app.state.runtime.register_project(manifest)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/requirements", response_model=list[Requirement])
    def list_requirements(
        request: Request, project_id: str | None = Query(default=None)
    ) -> list[Requirement]:
        ensure_path_namespace(request, project_id)
        return visible_items(request, app.state.runtime.list_requirements(project_id))

    @app.post("/v1/requirements", response_model=Requirement, status_code=201)
    def register_requirement(request: Request, requirement: Requirement) -> Requirement:
        requirement = ensure_namespace(request, requirement)  # type: ignore[assignment]
        try:
            return app.state.runtime.register_requirement(requirement)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/phases", response_model=list[ProjectPhase])
    def list_phases(
        request: Request, project_id: str | None = Query(default=None)
    ) -> list[ProjectPhase]:
        ensure_path_namespace(request, project_id)
        return visible_items(request, app.state.runtime.list_phases(project_id))

    @app.post("/v1/phases", response_model=ProjectPhase, status_code=201)
    def register_phase(request: Request, phase: ProjectPhase) -> ProjectPhase:
        phase = ensure_namespace(request, phase)  # type: ignore[assignment]
        try:
            return app.state.runtime.register_phase(phase)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/phases/{phase_id}/approve", response_model=ProjectPhase)
    def approve_phase(request: Request, phase_id: str, payload: dict[str, str]) -> ProjectPhase:
        phase = getattr(app.state.runtime, "phases", {}).get(phase_id)
        if phase is not None:
            ensure_namespace(request, phase)
        try:
            return app.state.runtime.approve_phase(phase_id, approver=payload.get("approver", ""))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/tasks", response_model=list[TaskEnvelope])
    def list_tasks(request: Request) -> list[TaskEnvelope]:
        return visible_items(request, app.state.runtime.list_tasks())

    @app.get("/v1/tasks/{task_id}", response_model=TaskEnvelope)
    def get_task(request: Request, task_id: str) -> TaskEnvelope:
        try:
            task = app.state.runtime.get_task(task_id)
            return ensure_namespace(request, task)  # type: ignore[return-value]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/tasks/{task_id}/result", response_model=AgentResult)
    def get_task_result(task_id: str) -> AgentResult:
        try:
            return app.state.runtime.get_result(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/tasks/{task_id}/cancel", response_model=TaskEnvelope)
    def cancel_task(request: Request, task_id: str) -> TaskEnvelope:
        if tenant_context_required and hasattr(app.state.runtime, "get_task"):
            try:
                ensure_namespace(request, app.state.runtime.get_task(task_id))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            return app.state.runtime.cancel_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/tasks/{task_id}/retry", response_model=TaskEnvelope)
    def retry_task(request: Request, task_id: str) -> TaskEnvelope:
        if tenant_context_required and hasattr(app.state.runtime, "get_task"):
            try:
                ensure_namespace(request, app.state.runtime.get_task(task_id))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            return app.state.runtime.retry_task(task_id)
        except QueueCapacityError as exc:
            raise HTTPException(
                status_code=429,
                detail={"code": "queue_full", "message": "La cola de tareas está llena"},
                headers={"Retry-After": "1"},
            ) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/tasks/{task_id}/approve", response_model=TaskEnvelope)
    def approve_task(request: Request, task_id: str, payload: dict[str, str]) -> TaskEnvelope:
        if tenant_context_required and hasattr(app.state.runtime, "get_task"):
            try:
                ensure_namespace(request, app.state.runtime.get_task(task_id))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            return app.state.runtime.approve_task(task_id, approver=payload.get("approver", ""))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except QueueCapacityError as exc:
            raise HTTPException(
                status_code=429,
                detail={"code": "queue_full", "message": str(exc)},
            ) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/agents")
    def list_agents(request: Request) -> list[dict[str, object]]:
        if not tenant_context_required:
            return app.state.runtime.list_agents()
        visible_task_ids = {
            task.task_id
            for task in visible_items(request, app.state.runtime.list_tasks())
        }
        return [
            agent
            for agent in app.state.runtime.list_agents()
            if any(
                task.task_id in visible_task_ids
                for task in app.state.runtime.list_tasks()
                if task.actor == agent.get("agent_id")
            )
        ]

    @app.get("/v1/overview")
    def overview(
        request: Request, project_id: str | None = Query(default=None)
    ) -> dict[str, object]:
        ensure_path_namespace(request, project_id)
        if tenant_context_required and project_id is None:
            project_id = request_context(request).project_id
        return visible_overview(request, app.state.runtime.overview(project_id))

    @app.post("/v1/tasks", status_code=202)
    def submit_task(request: Request, task: TaskEnvelope) -> dict[str, str]:
        task = ensure_namespace(request, task)  # type: ignore[assignment]
        try:
            task_id = app.state.runtime.submit_task(task)
        except QueueCapacityError as exc:
            raise HTTPException(
                status_code=429,
                detail={"code": "queue_full", "message": "La cola de tareas está llena"},
                headers={"Retry-After": "1"},
            ) from exc
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"task_id": task_id, "status": "accepted"}

    @app.post("/v1/results", status_code=202)
    def record_result(request: Request, result: AgentResult) -> dict[str, str]:
        if tenant_context_required:
            try:
                ensure_namespace(request, app.state.runtime.get_task(result.task_id))
            except KeyError as exc:
                raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            app.state.runtime.record_result(result)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"task_id": result.task_id, "status": "recorded"}

    @app.post("/v1/memory/candidates", status_code=201)
    def capture_memory(request: Request, candidate: MemoryCandidate) -> dict[str, str]:
        candidate = ensure_namespace(request, candidate)  # type: ignore[assignment]
        try:
            candidate_id = app.state.runtime.capture_memory(candidate)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"candidate_id": candidate_id, "status": "stored"}

    @app.get("/v1/memory/candidates", response_model=list[MemoryCandidate])
    def list_memory_candidates(
        request: Request,
        organization_id: str = Query(default="default", min_length=1),
        project_id: str = Query(min_length=1),
    ) -> list[MemoryCandidate]:
        if tenant_context_required:
            context = request_context(request)
            if organization_id not in {"default", context.organization_id}:
                raise HTTPException(status_code=403, detail="Organizacion no autorizada")
            organization_id = context.organization_id
            ensure_path_namespace(request, project_id)
        try:
            return app.state.runtime.list_memory_candidates(organization_id, project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/memory/candidates/{candidate_id}", response_model=MemoryCandidate)
    def get_memory_candidate(
        candidate_id: str,
        organization_id: str = Query(min_length=1),
        project_id: str = Query(min_length=1),
    ) -> MemoryCandidate:
        try:
            return app.state.runtime.get_memory_candidate(
                candidate_id, organization_id=organization_id, project_id=project_id
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/memory/candidates/{candidate_id}/validate", response_model=MemoryCandidate)
    def validate_memory_candidate(
        candidate_id: str,
        payload: dict[str, str],
        organization_id: str = Query(min_length=1),
        project_id: str = Query(min_length=1),
    ) -> MemoryCandidate:
        try:
            return app.state.runtime.review_memory_candidate(
                candidate_id,
                reviewer=payload.get("reviewer", ""),
                status="validated",
                organization_id=organization_id,
                project_id=project_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/memory/candidates/{candidate_id}/reject", response_model=MemoryCandidate)
    def reject_memory_candidate(
        candidate_id: str,
        payload: dict[str, str],
        organization_id: str = Query(min_length=1),
        project_id: str = Query(min_length=1),
    ) -> MemoryCandidate:
        try:
            return app.state.runtime.review_memory_candidate(
                candidate_id,
                reviewer=payload.get("reviewer", ""),
                status="rejected",
                organization_id=organization_id,
                project_id=project_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/memory/search", response_model=list[MemoryCandidate])
    def search_memory(
        request: Request, search_request: MemorySearchRequest
    ) -> list[MemoryCandidate]:
        search_request = ensure_namespace(request, search_request)  # type: ignore[assignment]
        try:
            return app.state.runtime.search_memory(
                search_request.organization_id,
                search_request.project_id,
                search_request.query,
                search_request.agent_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/knowledge/promotions", status_code=201)
    def promote(request: Request, promotion: PromotionRequest) -> dict[str, str]:
        promotion = ensure_namespace(request, promotion)  # type: ignore[assignment]
        try:
            promotion_id = app.state.runtime.promote(promotion)
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"promotion_id": promotion_id, "status": "published"}

    @app.get("/v1/events", response_model=list[OperationEvent])
    def list_events(
        request: Request, limit: int = Query(default=100, ge=1, le=1000)
    ) -> list[OperationEvent]:
        events = app.state.runtime.list_events(limit)
        if tenant_context_required:
            context = request_context(request)
            events = [
                event
                for event in events
                if event.organization_id == context.organization_id
                and (
                    context.project_id is None
                    or event.project_id == context.project_id
                )
            ]
        return events

    @app.get("/v1/tasks/{task_id}/timeline", response_model=list[TimelineEntry])
    def task_timeline(
        request: Request, task_id: str, limit: int = Query(default=100, ge=1, le=1000)
    ) -> list[TimelineEntry]:
        try:
            ensure_namespace(request, app.state.runtime.get_task(task_id))
            return app.state.runtime.task_timeline(task_id, limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/phases/{phase_id}/timeline", response_model=list[TimelineEntry])
    def phase_timeline(
        request: Request, phase_id: str, limit: int = Query(default=100, ge=1, le=1000)
    ) -> list[TimelineEntry]:
        try:
            phase = app.state.runtime.phases.get(phase_id)
            if phase is not None:
                ensure_namespace(request, phase)
            return app.state.runtime.phase_timeline(phase_id, limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/logs", response_model=list[TaskLog])
    def list_logs(
        request: Request,
        organization_id: str | None = Query(default=None),
        project_id: str | None = Query(default=None),
        task_id: str | None = Query(default=None),
        phase_id: str | None = Query(default=None),
        requirement_id: str | None = Query(default=None),
        level: LogLevel | None = None,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[TaskLog]:
        if tenant_context_required:
            context = request_context(request)
            if organization_id not in {None, context.organization_id}:
                raise HTTPException(status_code=403, detail="Organizacion no autorizada")
            organization_id = context.organization_id
            ensure_path_namespace(request, project_id)
            project_id = project_id or context.project_id
        return app.state.runtime.list_logs(
            organization_id=organization_id,
            project_id=project_id,
            task_id=task_id,
            phase_id=phase_id,
            requirement_id=requirement_id,
            level=level,
            limit=limit,
        )

    @app.post("/v1/logs", response_model=TaskLog, status_code=201)
    def record_log(request: Request, log: TaskLog) -> TaskLog:
        log = ensure_namespace(request, log)  # type: ignore[assignment]
        try:
            return app.state.runtime.record_task_log(log)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/plans/{proposal_id}", response_model=PlanProposal)
    def get_plan(request: Request, proposal_id: str) -> PlanProposal:
        try:
            proposal = app.state.runtime.get_plan_proposal(proposal_id)
            return ensure_namespace(request, proposal)  # type: ignore[return-value]
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/plans", response_model=PlanProposal, status_code=201)
    def register_plan(request: Request, proposal: PlanProposal) -> PlanProposal:
        proposal = ensure_namespace(request, proposal)  # type: ignore[assignment]
        try:
            return app.state.runtime.register_plan_proposal(proposal)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/plans/{proposal_id}/approve", response_model=PlanProposal)
    def approve_plan(request: Request, proposal_id: str, payload: dict[str, str]) -> PlanProposal:
        try:
            proposal = app.state.runtime.get_plan_proposal(proposal_id)
            ensure_namespace(request, proposal)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        try:
            return app.state.runtime.approve_plan(
                proposal_id, approver=payload.get("approver", "")
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app
