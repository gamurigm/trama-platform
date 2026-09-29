"""HTTP coordination adapter for a CCCC bridge running on the Windows host."""

from __future__ import annotations

from urllib.parse import urlsplit

import httpx

from .contracts import AgentResult, TaskEnvelope
from .ports import CoordinationPort


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

    def submit_task(self, task: TaskEnvelope) -> str:
        response = self._client.post("/v1/tasks", json=task.model_dump(mode="json"))
        response.raise_for_status()
        payload = response.json()
        tracking_id = payload.get("tracking_id") if isinstance(payload, dict) else None
        if not isinstance(tracking_id, str) or not tracking_id:
            raise ValueError("CCCC bridge response did not include a tracking ID")
        return tracking_id

    def record_result(self, result: AgentResult) -> None:
        response = self._client.post("/v1/results", json=result.model_dump(mode="json"))
        response.raise_for_status()

    def close(self) -> None:
        self._client.close()
