"""Construccion del coordinador de tareas segun la configuracion."""

from __future__ import annotations

from .adapters import CcccCliAdapter
from .cccc_bridge_client import CcccBridgeCoordination
from .ports import CoordinationPort
from .settings import TramaSettings


def build_coordination(settings: TramaSettings) -> CoordinationPort | None:
    """Construye el coordinador externo solicitado por configuración."""

    backend = settings.coordination_backend.casefold()
    if backend == "memory":
        return None
    if backend == "cccc":
        return CcccCliAdapter(
            executable=settings.cccc_executable,
            timeout_seconds=settings.cccc_timeout_seconds,
        )
    if backend == "cccc-bridge":
        return CcccBridgeCoordination(
            base_url=settings.cccc_bridge_url,
            token=settings.cccc_bridge_token or "",
            timeout_seconds=settings.cccc_bridge_timeout_seconds,
        )
    raise ValueError(
        "TRAMA_COORDINATION_BACKEND debe ser 'memory', 'cccc' o 'cccc-bridge'"
    )
