"""Configuracion tipada de TRAMA desde variables de entorno."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


def _read_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} debe ser un entero") from exc


def _read_positive_int(name: str, default: int) -> int:
    value = _read_int(name, default)
    if value < 1:
        raise ValueError(f"{name} debe ser mayor que cero")
    return value


def _read_bool(name: str, default: bool) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    normalized = raw.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(f"{name} debe ser booleano")


def _read_url(name: str, default: str, *, allow_empty: bool = False) -> str:
    value = os.getenv(name, default).strip()
    if allow_empty and not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc or not parsed.hostname:
        raise ValueError(f"{name} debe ser una URL HTTP(S) con host")
    return value


def _default_hermes_config_path() -> str:
    hermes_home = os.getenv("HERMES_HOME")
    if hermes_home:
        return str(Path(hermes_home) / "config.yaml")
    if os.name == "nt":
        local_app_data = os.getenv("LOCALAPPDATA")
        if local_app_data:
            return str(Path(local_app_data) / "hermes" / "config.yaml")
    return "~/.hermes/config.yaml"


@dataclass(frozen=True)
class TramaSettings:
    environment: str = "local"
    organization_id: str = "default"
    state_dir: str = "artifacts/state"
    api_host: str = "127.0.0.1"
    api_port: int = 8090
    api_url: str = "http://127.0.0.1:8090"
    coordination_backend: str = "memory"
    cccc_executable: str = "cccc"
    cccc_timeout_seconds: int = 30
    queue_capacity: int = 100
    max_concurrency: int = 4
    dispatch_timeout_seconds: int = 900
    hermes_executable: str = "hermes"
    hermes_config_path: str = "~/.hermes/config.yaml"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    colibri_url: str = "http://127.0.0.1:8020"
    colibri_model: str = "olmoe-1b-7b-0125-instruct"
    colibri_executable: str = "coli"
    semantica_enabled: bool = False
    semantica_executable: str = "semantica-mcp"
    utopia_url: str = "http://127.0.0.1:1516"
    utopia_mcp_url: str = ""

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
            api_url=_read_url("TRAMA_API_URL", f"http://{api_host}:{api_port}"),
            coordination_backend=os.getenv("TRAMA_COORDINATION_BACKEND", "memory"),
            cccc_executable=os.getenv("TRAMA_CCCC_EXECUTABLE", "cccc"),
            cccc_timeout_seconds=_read_int("TRAMA_CCCC_TIMEOUT_SECONDS", 30),
            queue_capacity=_read_positive_int("TRAMA_QUEUE_CAPACITY", 100),
            max_concurrency=_read_positive_int("TRAMA_MAX_CONCURRENCY", 4),
            dispatch_timeout_seconds=_read_positive_int(
                "TRAMA_DISPATCH_TIMEOUT_SECONDS", 900
            ),
            hermes_executable=os.getenv("TRAMA_HERMES_EXECUTABLE", "hermes"),
            hermes_config_path=os.getenv(
                "TRAMA_HERMES_CONFIG_PATH", _default_hermes_config_path()
            ),
            ollama_url=_read_url("TRAMA_OLLAMA_URL", "http://127.0.0.1:11434"),
            ollama_model=os.getenv("TRAMA_OLLAMA_MODEL", "qwen3:8b"),
            colibri_url=_read_url("TRAMA_COLIBRI_URL", "http://127.0.0.1:8020"),
            colibri_model=os.getenv(
                "TRAMA_COLIBRI_MODEL", "olmoe-1b-7b-0125-instruct"
            ),
            colibri_executable=os.getenv("TRAMA_COLIBRI_EXECUTABLE", "coli"),
            semantica_enabled=_read_bool("TRAMA_SEMANTICA_ENABLED", False),
            semantica_executable=os.getenv(
                "TRAMA_SEMANTICA_EXECUTABLE", "semantica-mcp"
            ),
            utopia_url=_read_url("TRAMA_UTOPIA_URL", "http://127.0.0.1:1516"),
            utopia_mcp_url=_read_url("TRAMA_UTOPIA_MCP_URL", "", allow_empty=True),
        )
