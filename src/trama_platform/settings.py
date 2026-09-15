"""Configuracion tipada de TRAMA desde variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} debe ser un entero") from exc


@dataclass(frozen=True)
class TramaSettings:
    environment: str = "local"
    organization_id: str = "default"
    state_dir: str = "artifacts/state"
    api_host: str = "127.0.0.1"
    api_port: int = 8090
    api_url: str = "http://127.0.0.1:8090"
    cccc_executable: str = "cccc"
    cccc_timeout_seconds: int = 30
    hermes_executable: str = "hermes"
    hermes_config_path: str = "~/.hermes/config.yaml"

    @property
    def state_path(self) -> Path:
        return Path(self.state_dir) / "trama.db"

    @classmethod
    def from_env(cls) -> "TramaSettings":
        api_host = os.getenv("TRAMA_API_HOST", "127.0.0.1")
        api_port = _read_int("TRAMA_API_PORT", 8090)
        return cls(
            environment=os.getenv("TRAMA_ENV", "local"),
            organization_id=os.getenv("TRAMA_ORGANIZATION_ID", "default"),
            state_dir=os.getenv("TRAMA_STATE_DIR", "artifacts/state"),
            api_host=api_host,
            api_port=api_port,
            api_url=os.getenv("TRAMA_API_URL", f"http://{api_host}:{api_port}"),
            cccc_executable=os.getenv("TRAMA_CCCC_EXECUTABLE", "cccc"),
            cccc_timeout_seconds=_read_int("TRAMA_CCCC_TIMEOUT_SECONDS", 30),
            hermes_executable=os.getenv("TRAMA_HERMES_EXECUTABLE", "hermes"),
            hermes_config_path=os.getenv(
                "TRAMA_HERMES_CONFIG_PATH", "~/.hermes/config.yaml"
            ),
        )
