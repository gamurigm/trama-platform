"""Catalogo de servicios locales opcionales de TRAMA."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Literal
from urllib.parse import urlsplit, urlunsplit

import httpx

from .settings import TramaSettings

ServiceState = Literal["ready", "missing", "unavailable", "disabled", "error"]


@dataclass(frozen=True)
class ServiceStatus:
    """Estado serializable y no sensible de un servicio local."""

    id: str
    status: ServiceState
    kind: str
    message: str
    endpoint: str | None = None
    executable: str | None = None
    model: str | None = None

    def __post_init__(self) -> None:
        if self.endpoint is not None:
            object.__setattr__(self, "endpoint", _sanitize_endpoint(self.endpoint))

    def as_dict(self) -> dict[str, object]:
        result: dict[str, object] = {
            "id": self.id,
            "status": self.status,
            "kind": self.kind,
            "message": self.message,
        }
        if self.endpoint is not None:
            result["endpoint"] = self.endpoint
        if self.executable is not None:
            result["executable"] = self.executable
        if self.model is not None:
            result["model"] = self.model
        return result


def _sanitize_endpoint(endpoint: str) -> str | None:
    """Conserva solo el destino HTTP publico, nunca userinfo ni query data."""

    try:
        parsed = urlsplit(endpoint)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            return None
        hostname = parsed.hostname
        if ":" in hostname and not hostname.startswith("["):
            hostname = f"[{hostname}]"
        port = f":{parsed.port}" if parsed.port is not None else ""
        return urlunsplit((parsed.scheme, f"{hostname}{port}", parsed.path, "", ""))
    except ValueError:
        return None


def _service_url(endpoint: str, suffix: str = "") -> str:
    safe_endpoint = _sanitize_endpoint(endpoint)
    if safe_endpoint is None:
        return ""
    if not suffix:
        return safe_endpoint
    return f"{safe_endpoint.rstrip('/')}/{suffix.lstrip('/')}"


def _check_http(
    *,
    service_id: str,
    endpoint: str,
    url: str,
    model: str | None = None,
    model_field: str | None = None,
) -> ServiceStatus:
    safe_url = _sanitize_endpoint(url)
    if safe_url is None:
        return ServiceStatus(
            id=service_id,
            status="error",
            kind="http",
            endpoint=endpoint,
            model=model,
            message="endpoint invalido",
        )
    try:
        with httpx.Client(timeout=2) as client:
            response = client.get(safe_url)
            response.raise_for_status()
    except httpx.TimeoutException:
        return ServiceStatus(
            id=service_id,
            status="unavailable",
            kind="http",
            endpoint=endpoint,
            model=model,
            message="sin respuesta dentro del tiempo limite",
        )
    except (httpx.HTTPError, OSError) as exc:
        return ServiceStatus(
            id=service_id,
            status="unavailable",
            kind="http",
            endpoint=endpoint,
            model=model,
            message=f"endpoint no disponible ({type(exc).__name__})",
        )
    if model is not None and model_field is not None:
        try:
            payload = response.json()
            models = payload.get(model_field, []) if isinstance(payload, dict) else []
        except ValueError:
            return ServiceStatus(
                id=service_id,
                status="unavailable",
                kind="http",
                endpoint=endpoint,
                model=model,
                message="respuesta de modelos invalida",
            )
        if not isinstance(models, list) or not any(
            isinstance(item, dict) and item.get("name", item.get("id")) == model
            for item in models
        ):
            return ServiceStatus(
                id=service_id,
                status="unavailable",
                kind="http",
                endpoint=endpoint,
                model=model,
                message="modelo configurado no encontrado",
            )
    return ServiceStatus(
        id=service_id,
        status="ready",
        kind="http",
        endpoint=endpoint,
        model=model,
        message="endpoint disponible",
    )


def _check_mcp(endpoint: str) -> ServiceStatus:
    safe_endpoint = _sanitize_endpoint(endpoint)
    if safe_endpoint is None:
        return ServiceStatus(
            id="utopia",
            status="error",
            kind="mcp",
            endpoint=endpoint,
            message="endpoint MCP invalido",
        )
    initialize_request = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "initialize",
        "params": {
            "protocolVersion": "2025-03-26",
            "capabilities": {},
            "clientInfo": {"name": "trama-service-catalog", "version": "0.1.0"},
        },
    }
    try:
        with httpx.Client(timeout=2) as client:
            response = client.post(safe_endpoint, json=initialize_request)
            response.raise_for_status()
            payload = response.json()
    except httpx.TimeoutException:
        return ServiceStatus(
            id="utopia",
            status="unavailable",
            kind="mcp",
            endpoint=endpoint,
            message="MCP sin respuesta dentro del tiempo limite",
        )
    except (httpx.HTTPError, OSError):
        return ServiceStatus(
            id="utopia",
            status="unavailable",
            kind="mcp",
            endpoint=endpoint,
            message="MCP no disponible o no autorizado",
        )
    except ValueError:
        return ServiceStatus(
            id="utopia",
            status="unavailable",
            kind="mcp",
            endpoint=endpoint,
            message="respuesta MCP invalida",
        )
    if not isinstance(payload, dict) or "result" not in payload or "error" in payload:
        return ServiceStatus(
            id="utopia",
            status="unavailable",
            kind="mcp",
            endpoint=endpoint,
            message="MCP no disponible o no autorizado",
        )
    return ServiceStatus(
        id="utopia",
        status="ready",
        kind="mcp",
        endpoint=endpoint,
        message="MCP inicializado",
    )


def _check_semantica(settings: TramaSettings) -> ServiceStatus:
    executable = settings.semantica_executable
    if shutil.which(executable) is None:
        return ServiceStatus(
            id="semantica",
            status="missing",
            kind="mcp",
            executable=executable,
            message="ejecutable no encontrado",
        )
    return ServiceStatus(
        id="semantica",
        status="ready",
        kind="mcp",
        executable=executable,
        message="ejecutable disponible",
    )


def collect_service_status(settings: TramaSettings) -> dict[str, object]:
    """Comprueba servicios locales sin leer secretos ni lanzar procesos."""

    services = [
        _check_http(
            service_id="trama",
            endpoint=settings.api_url,
            url=_service_url(settings.api_url, "/health"),
        ),
        _check_http(
            service_id="ollama",
            endpoint=settings.ollama_url,
            url=_service_url(settings.ollama_url, "/api/tags"),
            model=settings.ollama_model,
            model_field="models",
        ),
        _check_http(
            service_id="colibri",
            endpoint=settings.colibri_url,
            url=_service_url(settings.colibri_url, "/v1/models"),
            model=settings.colibri_model,
            model_field="data",
        ),
    ]
    if settings.utopia_mcp_url:
        services.append(_check_mcp(settings.utopia_mcp_url))
    else:
        utopia_url = settings.utopia_url or "http://127.0.0.1:1516"
        services.append(
            _check_http(
                service_id="utopia",
                endpoint=utopia_url,
                url=_service_url(utopia_url),
            )
        )
    if settings.semantica_enabled:
        services.append(_check_semantica(settings))

    statuses = [service.status for service in services]
    overall: ServiceState = "ready" if "ready" in statuses else "unavailable"
    return {"status": overall, "services": [service.as_dict() for service in services]}
