"""API HTTP mínima para integrar proyectos sin compartir sus dependencias."""

from __future__ import annotations

from contextlib import asynccontextmanager
from hmac import compare_digest

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

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
    runtime_instance = runtime or TramaRuntime(
        coordination=coordination,
        context_memory=context_memory,
        canonical_knowledge=canonical_knowledge,
        state_store=state_store,
        queue_capacity=settings.queue_capacity if settings else 100,
        max_concurrency=settings.max_concurrency if settings else 4,
        dispatch_timeout_seconds=(settings.dispatch_timeout_seconds if settings else 900),
    )

    @asynccontextmanager
    async def lifespan(_: FastAPI):
        yield
        runtime_instance.close()

    app = FastAPI(title="TRAMA", version="0.1.0", lifespan=lifespan)
    app.state.runtime = runtime_instance

    from .config_contracts import register_config_routes

    register_config_routes(app, settings or TramaSettings())

    @app.exception_handler(RequestValidationError)
    async def validation_error(_: Request, exc: RequestValidationError):
        # Pydantic's default error includes raw inputs, including credential payloads.
        return JSONResponse(
            status_code=422,
            content={
                "detail": [
                    {
                        "loc": list(error["loc"]),
                        "type": error["type"],
                        "msg": "Valor no válido; revisa el campo indicado",
                    }
                    for error in exc.errors()
                ]
            },
        )

    @app.middleware("http")
    async def require_api_token(request: Request, call_next):
        expected = settings.api_token if settings else None
        if expected and request.url.path != "/health":
            authorization = request.headers.get("authorization", "")
            scheme, _, supplied = authorization.partition(" ")
            if scheme.casefold() != "bearer" or not compare_digest(
                supplied.encode("utf-8"), expected.encode("utf-8")
            ):
                return JSONResponse(
                    status_code=401,
                    content={"detail": "Se requiere un token Bearer válido"},
                    headers={"WWW-Authenticate": "Bearer"},
                )
        return await call_next(request)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "trama"}

    @app.get("/v1/status")
    def status() -> dict[str, object]:
        return app.state.runtime.status()

    @app.get("/v1/projects", response_model=list[ProjectManifest])
    def list_projects() -> list[ProjectManifest]:
        return app.state.runtime.list_projects()

    @app.get("/v1/projects/{project_id}", response_model=ProjectManifest)
    def get_project(project_id: str) -> ProjectManifest:
        try:
            return app.state.runtime.get_project(project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/projects", response_model=ProjectManifest, status_code=201)
    def register_project(manifest: ProjectManifest) -> ProjectManifest:
        try:
            return app.state.runtime.register_project(manifest)
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/requirements", response_model=list[Requirement])
    def list_requirements(project_id: str | None = Query(default=None)) -> list[Requirement]:
        return app.state.runtime.list_requirements(project_id)

    @app.post("/v1/requirements", response_model=Requirement, status_code=201)
    def register_requirement(requirement: Requirement) -> Requirement:
        try:
            return app.state.runtime.register_requirement(requirement)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/phases", response_model=list[ProjectPhase])
    def list_phases(project_id: str | None = Query(default=None)) -> list[ProjectPhase]:
        return app.state.runtime.list_phases(project_id)

    @app.post("/v1/phases", response_model=ProjectPhase, status_code=201)
    def register_phase(phase: ProjectPhase) -> ProjectPhase:
        try:
            return app.state.runtime.register_phase(phase)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/phases/{phase_id}/approve", response_model=ProjectPhase)
    def approve_phase(phase_id: str, payload: dict[str, str]) -> ProjectPhase:
        try:
            return app.state.runtime.approve_phase(phase_id, approver=payload.get("approver", ""))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/tasks", response_model=list[TaskEnvelope])
    def list_tasks() -> list[TaskEnvelope]:
        return app.state.runtime.list_tasks()

    @app.get("/v1/tasks/{task_id}", response_model=TaskEnvelope)
    def get_task(task_id: str) -> TaskEnvelope:
        try:
            return app.state.runtime.get_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/tasks/{task_id}/cancel", response_model=TaskEnvelope)
    def cancel_task(task_id: str) -> TaskEnvelope:
        try:
            return app.state.runtime.cancel_task(task_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/tasks/{task_id}/retry", response_model=TaskEnvelope)
    def retry_task(task_id: str) -> TaskEnvelope:
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
    def approve_task(task_id: str, payload: dict[str, str]) -> TaskEnvelope:
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
    def list_agents() -> list[dict[str, object]]:
        return app.state.runtime.list_agents()

    @app.get("/v1/overview")
    def overview(project_id: str | None = Query(default=None)) -> dict[str, object]:
        return app.state.runtime.overview(project_id)

    @app.post("/v1/tasks", status_code=202)
    def submit_task(task: TaskEnvelope) -> dict[str, str]:
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
    def record_result(result: AgentResult) -> dict[str, str]:
        try:
            app.state.runtime.record_result(result)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        return {"task_id": result.task_id, "status": "recorded"}

    @app.post("/v1/memory/candidates", status_code=201)
    def capture_memory(candidate: MemoryCandidate) -> dict[str, str]:
        try:
            candidate_id = app.state.runtime.capture_memory(candidate)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"candidate_id": candidate_id, "status": "stored"}

    @app.get("/v1/memory/candidates", response_model=list[MemoryCandidate])
    def list_memory_candidates(
        organization_id: str = Query(default="default", min_length=1),
        project_id: str = Query(min_length=1),
    ) -> list[MemoryCandidate]:
        try:
            return app.state.runtime.list_memory_candidates(organization_id, project_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/memory/search", response_model=list[MemoryCandidate])
    def search_memory(request: MemorySearchRequest) -> list[MemoryCandidate]:
        try:
            return app.state.runtime.search_memory(
                request.organization_id,
                request.project_id,
                request.query,
                request.agent_id,
            )
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/knowledge/promotions", status_code=201)
    def promote(request: PromotionRequest) -> dict[str, str]:
        try:
            promotion_id = app.state.runtime.promote(request)
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"promotion_id": promotion_id, "status": "published"}

    @app.get("/v1/events", response_model=list[OperationEvent])
    def list_events(limit: int = Query(default=100, ge=1, le=1000)) -> list[OperationEvent]:
        return app.state.runtime.list_events(limit)

    @app.get("/v1/tasks/{task_id}/timeline", response_model=list[TimelineEntry])
    def task_timeline(
        task_id: str, limit: int = Query(default=100, ge=1, le=1000)
    ) -> list[TimelineEntry]:
        try:
            return app.state.runtime.task_timeline(task_id, limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/phases/{phase_id}/timeline", response_model=list[TimelineEntry])
    def phase_timeline(
        phase_id: str, limit: int = Query(default=100, ge=1, le=1000)
    ) -> list[TimelineEntry]:
        try:
            return app.state.runtime.phase_timeline(phase_id, limit)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.get("/v1/logs", response_model=list[TaskLog])
    def list_logs(
        organization_id: str | None = Query(default=None),
        project_id: str | None = Query(default=None),
        task_id: str | None = Query(default=None),
        phase_id: str | None = Query(default=None),
        requirement_id: str | None = Query(default=None),
        level: LogLevel | None = None,
        limit: int = Query(default=100, ge=1, le=1000),
    ) -> list[TaskLog]:
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
    def record_log(log: TaskLog) -> TaskLog:
        try:
            return app.state.runtime.record_task_log(log)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/plans", response_model=list[PlanProposal])
    def list_plans() -> list[PlanProposal]:
        return app.state.runtime.list_plan_proposals()

    @app.get("/v1/plans/{proposal_id}", response_model=PlanProposal)
    def get_plan(proposal_id: str) -> PlanProposal:
        try:
            return app.state.runtime.get_plan_proposal(proposal_id)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc

    @app.post("/v1/plans", response_model=PlanProposal, status_code=201)
    def register_plan(proposal: PlanProposal) -> PlanProposal:
        try:
            return app.state.runtime.register_plan_proposal(proposal)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.post("/v1/plans/{proposal_id}/approve", response_model=PlanProposal)
    def approve_plan(proposal_id: str, payload: dict[str, str]) -> PlanProposal:
        try:
            return app.state.runtime.approve_plan(proposal_id, approver=payload.get("approver", ""))
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    return app
