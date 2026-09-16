"""Adaptador local de inferencia Colibri para agentes gestionados por Python."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from typing import Any

import httpx

from .contracts import ModelRequest, ModelResult
from .ports import ModelGatewayPort

PromptResolver = Callable[[ModelRequest], Sequence[Mapping[str, str]]]
ResultSink = Callable[[ModelRequest, str], str]


class ColibriModelGateway(ModelGatewayPort):
    """Usa la API OpenAI-compatible de una instancia Colibri local.

    Los prompts y las respuestas se resuelven mediante puertos del control
    plane. El adaptador solo transporta inferencia y nunca persiste secretos o
    contenido de agentes.
    """

    def __init__(
        self,
        base_url: str,
        *,
        model_id: str,
        prompt_resolver: PromptResolver,
        result_sink: ResultSink,
        api_key: str | None = None,
        timeout: float = 300.0,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self.model_id = model_id
        self.prompt_resolver = prompt_resolver
        self.result_sink = result_sink
        self.client = httpx.Client(
            base_url=base_url.rstrip("/"),
            timeout=timeout,
            transport=transport,
            headers={"Authorization": f"Bearer {api_key}"} if api_key else None,
        )

    def complete(self, request: ModelRequest) -> ModelResult:
        try:
            response = self.client.post(
                "/v1/chat/completions",
                json={
                    "model": self.model_id,
                    "messages": list(self.prompt_resolver(request)),
                    "stream": False,
                },
            )
            response.raise_for_status()
            content = _content_from(response.json())
            output_reference = self.result_sink(request, content)
        except (httpx.HTTPError, KeyError, TypeError, ValueError) as exc:
            return ModelResult(
                request_id=request.request_id,
                status="failed",
                provider="colibri",
                model=self.model_id,
                error=_safe_error(exc),
            )
        return ModelResult(
            request_id=request.request_id,
            status="succeeded",
            output_reference=output_reference,
            provider="colibri",
            model=self.model_id,
        )

    def close(self) -> None:
        self.client.close()


def _content_from(payload: Mapping[str, Any]) -> str:
    choices = payload["choices"]
    if not isinstance(choices, list) or not choices:
        raise ValueError("Colibri returned no choices")
    message = choices[0]["message"]
    content = message["content"]
    if not isinstance(content, str) or not content:
        raise ValueError("Colibri returned an empty completion")
    return content


def _safe_error(error: Exception) -> str:
    if isinstance(error, httpx.HTTPStatusError):
        return f"Colibri returned HTTP {error.response.status_code}"
    if isinstance(error, httpx.HTTPError):
        return "Colibri is unavailable"
    return "Colibri returned an invalid completion"
