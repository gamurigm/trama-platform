"""API HTTP mínima para integrar proyectos sin compartir sus dependencias."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException

from .contracts import AgentResult, MemoryCandidate, ProjectManifest, PromotionRequest, TaskEnvelope
from .runtime import TramaRuntime


def create_app(runtime: TramaRuntime | None = None) -> FastAPI:
    app = FastAPI(title="TRAMA", version="0.1.0")
    app.state.runtime = runtime or TramaRuntime()

    @app.get("/health")
    def health() -> dict[str, str]:
        return {"status": "ok", "service": "trama"}

    @app.post("/v1/projects", response_model=ProjectManifest, status_code=201)
    def register_project(manifest: ProjectManifest) -> ProjectManifest:
        return app.state.runtime.register_project(manifest)

    @app.post("/v1/tasks", status_code=202)
    def submit_task(task: TaskEnvelope) -> dict[str, str]:
        try:
            task_id = app.state.runtime.submit_task(task)
        except KeyError as exc:
            raise HTTPException(status_code=404, detail=str(exc)) from exc
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
        return {"candidate_id": candidate_id, "status": "stored"}

    @app.post("/v1/knowledge/promotions", status_code=201)
    def promote(request: PromotionRequest) -> dict[str, str]:
        try:
            promotion_id = app.state.runtime.promote(request)
        except (KeyError, PermissionError, ValueError) as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
        return {"promotion_id": promotion_id, "status": "published"}

    return app
