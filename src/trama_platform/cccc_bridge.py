"""Authenticated HTTP bridge from container workers to the local CCCC CLI."""

from __future__ import annotations

import subprocess
from hmac import compare_digest

from fastapi import FastAPI, HTTPException, Request, Response

from .adapters import CcccCliAdapter
from .contracts import AgentResult, TaskEnvelope
from .ports import CoordinationPort
from .settings import TramaSettings


def create_cccc_bridge_app(
    settings: TramaSettings,
    cccc: CoordinationPort | None = None,
) -> FastAPI:
    """Create the local bridge app without starting a listener."""

    if not settings.cccc_bridge_token:
        raise ValueError("TRAMA_CCCC_BRIDGE_TOKEN is required")
    if not settings.allowed_cccc_actors:
        raise ValueError("TRAMA_CCCC_ALLOWED_ACTORS must allow at least one actor")
    if not settings.cccc_result_recipient.strip():
        raise ValueError("TRAMA_CCCC_RESULT_RECIPIENT is required")

    coordination = cccc or CcccCliAdapter(
        executable=settings.cccc_executable,
        timeout_seconds=settings.cccc_timeout_seconds,
        result_recipient=settings.cccc_result_recipient,
    )
    app = FastAPI(title="TRAMA CCCC Bridge", version="0.1.0")

    def require_token(request: Request) -> None:
        authorization = request.headers.get("authorization", "")
        scheme, _, supplied = authorization.partition(" ")
        expected = settings.cccc_bridge_token or ""
        if scheme.casefold() != "bearer" or not compare_digest(
            supplied.encode("utf-8"), expected.encode("utf-8")
        ):
            raise HTTPException(
                status_code=401,
                detail="Se requiere un token Bearer válido",
                headers={"WWW-Authenticate": "Bearer"},
            )

    @app.get("/healthz")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.post("/v1/tasks", status_code=202)
    def submit_task(task: TaskEnvelope, request: Request) -> dict[str, str]:
        require_token(request)
        if task.actor not in settings.allowed_cccc_actors:
            raise HTTPException(status_code=403, detail="El actor CCCC no está permitido")
        try:
            tracking_id = coordination.submit_task(task)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="CCCC request timed out") from None
        except (OSError, subprocess.SubprocessError, RuntimeError):
            raise HTTPException(status_code=502, detail="CCCC task submission failed") from None
        return {"tracking_id": tracking_id or task.task_id}

    @app.post("/v1/results", status_code=204)
    def record_result(result: AgentResult, request: Request) -> Response:
        require_token(request)
        try:
            coordination.record_result(result)
        except subprocess.TimeoutExpired:
            raise HTTPException(status_code=504, detail="CCCC request timed out") from None
        except (OSError, subprocess.SubprocessError, RuntimeError):
            raise HTTPException(status_code=502, detail="CCCC result forwarding failed") from None
        return Response(status_code=204)

    return app
