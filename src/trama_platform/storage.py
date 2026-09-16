"""Selección del backend de estado según el modo de despliegue."""

from __future__ import annotations

from .settings import TramaSettings
from .state_store import PostgresStateStore, SqliteStateStore


def build_state_store(settings: TramaSettings):
    """Construye el backend de estado sin permitir SQLite en producción."""

    if settings.is_production and not settings.database_url:
        raise ValueError("TRAMA_DATABASE_URL es obligatorio en produccion")
    if settings.database_url or settings.state_backend == "postgres":
        if not settings.database_url:
            raise ValueError("database_url es obligatorio para el backend postgres")
        return PostgresStateStore(settings.database_url)
    return SqliteStateStore(settings.state_path)
