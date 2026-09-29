"""HTTP coordination adapter for a CCCC bridge running on the Windows host."""

from __future__ import annotations

import logging
from time import perf_counter
from urllib.parse import urlsplit

import httpx

from .contracts import AgentResult, TaskEnvelope
from .ports import CoordinationPort

logger = logging.getLogger(__name__)


class CcccBridgeCoordination(CoordinationPort):
    """Send task submissions and results to the authenticated host bridge."""

    def __init__(
        self,
        base_url: str,
        token: str,
        timeout_seconds: float = 35,
        *,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        try:
            parsed = urlsplit(base_url)
            _ = parsed.port
        except ValueError:
            parsed = None
        if (
            parsed is None
            or parsed.scheme not in {"http", "https"}
            or not parsed.hostname
            or parsed.username
            or parsed.password
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("CCCC bridge URL must be HTTP(S) without credentials")
        if not token:
            raise ValueError("CCCC bridge bearer token is required")
        if timeout_seconds <= 0:
            raise ValueError("CCCC bridge timeout must be positive")

        self._client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout_seconds,
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
        )
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def submit_task(self, task: TaskEnvelope) -> str:
        started = perf_counter()
        logger.info(
            "event=cccc_bridge_dispatch_started task_id=%s",
            task.task_id,
            extra={"event": "cccc_bridge_dispatch_started", "task_id": task.task_id},
        )
        try:
            response = self._client.post("/v1/tasks", json=task.model_dump(mode="json"))
            response.raise_for_status()
            payload = response.json()
            tracking_id = payload.get("tracking_id") if isinstance(payload, dict) else None
            if not isinstance(tracking_id, str) or not tracking_id:
                raise ValueError("CCCC bridge response did not include a tracking ID")
        except Exception as exc:
            dispatch_duration_ms = round((perf_counter() - started) * 1000, 3)
            logger.warning(
                "event=cccc_bridge_dispatch_failed task_id=%s status=failed "
                "dispatch_duration_ms=%.3f error_type=%s",
                task.task_id,
                dispatch_duration_ms,
                type(exc).__name__,
                extra={
                    "event": "cccc_bridge_dispatch_failed",
                    "task_id": task.task_id,
                    "status": "failed",
                    "dispatch_duration_ms": dispatch_duration_ms,
                    "error_type": type(exc).__name__,
                },
            )
            raise
        dispatch_duration_ms = round((perf_counter() - started) * 1000, 3)
        logger.info(
            "event=cccc_bridge_dispatch_completed task_id=%s tracking_id=%s "
            "status=success dispatch_duration_ms=%.3f",
            task.task_id,
            tracking_id,
            dispatch_duration_ms,
            extra={
                "event": "cccc_bridge_dispatch_completed",
                "task_id": task.task_id,
                "tracking_id": tracking_id,
                "status": "success",
                "dispatch_duration_ms": dispatch_duration_ms,
            },
        )
        return tracking_id

    def record_result(self, result: AgentResult) -> None:
        response = self._client.post("/v1/results", json=result.model_dump(mode="json"))
        response.raise_for_status()

    def close(self) -> None:
        self._client.close()
