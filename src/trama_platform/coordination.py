"""Construccion del coordinador de tareas segun la configuracion."""

from __future__ import annotations

from .adapters import CcccCliAdapter
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
    raise ValueError("TRAMA_COORDINATION_BACKEND debe ser 'memory' o 'cccc'")
