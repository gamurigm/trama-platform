"""API HTTP mínima para integrar proyectos sin compartir sus dependencias."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException, Query

from .contracts import (
    AgentResult,
    MemoryCandidate,
    MemorySearchRequest,
    OperationEvent,
    ProjectManifest,
    PromotionRequest,
    TaskEnvelope,
)
from .ports import StateStorePort
from .runtime import TramaRuntime


def create_app(
    runtime: TramaRuntime | None = None,
    *,
    state_store: StateStorePort | None = None,
) -> FastAPI:
    app = FastAPI(title="TRAMA", version="0.1.0")
    app.state.runtime = runtime or TramaRuntime(state_store=state_store)

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
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc

    @app.get("/v1/agents")
    def list_agents() -> list[dict[str, object]]:
        return app.state.runtime.list_agents()

    @app.post("/v1/tasks", status_code=202)
    def submit_task(task: TaskEnvelope) -> dict[str, str]:
        try:
            task_id = app.state.runtime.submit_task(task)
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
                request.organization_id, request.project_id, request.query
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

    return app
