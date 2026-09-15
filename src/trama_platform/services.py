"""Catalogo de servicios locales opcionales de TRAMA."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from typing import Literal

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


def _check_http(
    *,
    service_id: str,
    endpoint: str,
    url: str,
    model: str | None = None,
) -> ServiceStatus:
    try:
        with httpx.Client(timeout=2) as client:
            response = client.get(url)
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
    return ServiceStatus(
        id=service_id,
        status="ready",
        kind="http",
        endpoint=endpoint,
        model=model,
        message="endpoint disponible",
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
            url=f"{settings.api_url.rstrip('/')}/health",
        ),
        _check_http(
            service_id="ollama",
            endpoint=settings.ollama_url,
            url=f"{settings.ollama_url.rstrip('/')}/api/tags",
            model=settings.ollama_model,
        ),
        _check_http(
            service_id="colibri",
            endpoint=settings.colibri_url,
            url=f"{settings.colibri_url.rstrip('/')}/v1/models",
            model=settings.colibri_model,
        ),
        _check_http(
            service_id="utopia",
            endpoint=settings.utopia_url,
            url=settings.utopia_url,
        ),
    ]
    if settings.semantica_enabled:
        services.append(_check_semantica(settings))

    statuses = [service.status for service in services]
    overall: ServiceState = "ready" if "ready" in statuses else "unavailable"
    return {"status": overall, "services": [service.as_dict() for service in services]}
