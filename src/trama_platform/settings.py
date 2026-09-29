"""Configuracion tipada de TRAMA desde variables de entorno."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
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
    normalized = raw.casefold().strip()
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
    if (
        parsed.scheme not in {"http", "https"}
        or not parsed.netloc
        or not parsed.hostname
        or parsed.username is not None
        or parsed.password is not None
        or parsed.query
        or parsed.fragment
    ):
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
    database_url: str | None = None
    state_backend: str = "sqlite"
    require_tenant_context: bool = False
    api_host: str = "127.0.0.1"
    api_port: int = 8090
    api_url: str = "http://127.0.0.1:8090"
    api_token: str | None = None
    internal_service_token: str | None = None
    gateway_url: str | None = None
    gateway_token: str | None = None
    coordination_backend: str = "memory"
    cccc_executable: str = "cccc"
    cccc_timeout_seconds: int = 30
    queue_capacity: int = 100
    max_concurrency: int = 4
    dispatch_timeout_seconds: int = 900
    task_lease_seconds: int = 60
    semantica_kg_path: str | None = None
    utopia_url: str | None = None
    utopia_kb_id: str | None = None
    utopia_token: str | None = None
    colibri_url: str = "http://127.0.0.1:8020"
    colibri_model: str = "OLMoE-1B-7B-0125-Instruct"
    nats_url: str = "nats://127.0.0.1:4222"
    nats_stream: str = "TRAMA_EVENTS"
    nats_subject: str = "trama.task.admitted.v1"
    nats_durable: str = "trama-python-dispatch"
    nats_ack_wait_seconds: int = 30
    nats_max_deliver: int = 5
    hermes_executable: str = "hermes"
    hermes_config_path: str = "~/.hermes/config.yaml"
    ollama_url: str = "http://127.0.0.1:11434"
    ollama_model: str = "qwen3:8b"
    colibri_executable: str = "coli"
    semantica_enabled: bool = False
    semantica_executable: str = "semantica-mcp"
    utopia_mcp_url: str = ""

    @property
    def state_path(self) -> Path:
        root = Path(self.state_dir)
        if not root.is_absolute() and os.getenv("TRAMA_APP_ROOT"):
            root = Path(os.environ["TRAMA_APP_ROOT"]) / root
        return root / "trama.db"

    @property
    def is_production(self) -> bool:
        return self.environment.casefold() in {"prod", "production"}

    @classmethod
    def from_env(cls, *, store=None, vault=None) -> "TramaSettings":
        from .credential_store import SECRET_NAMES, CredentialStore
        from .user_config import UserConfigStore, env_name

        store = store or UserConfigStore()
        vault = vault or CredentialStore()
        values = asdict(cls())
        values["hermes_config_path"] = _default_hermes_config_path()
        values.update(store.read())
        for name in SECRET_NAMES:
            values[name] = os.getenv(env_name(name)) or vault.get(name) or None
        for name, default in asdict(cls()).items():
            raw = os.getenv(env_name(name))
            if raw is not None and name not in SECRET_NAMES:
                if isinstance(default, bool):
                    values[name] = _read_bool(env_name(name), default)
                elif isinstance(default, int):
                    try:
                        values[name] = int(raw)
                    except ValueError:
                        raise ValueError(f"{env_name(name)} debe ser un entero") from None
                    if values[name] < 1:
                        raise ValueError(f"{env_name(name)} debe ser mayor que cero")
                else:
                    values[name] = raw or default
        values["api_url"] = (
            os.getenv("TRAMA_API_URL") or f"http://{values['api_host']}:{values['api_port']}"
        )
        environment = os.getenv("TRAMA_ENV", values["environment"])
        database_url = os.getenv("TRAMA_DATABASE_URL") or None
        is_production = environment.casefold() in {"prod", "production"}
        if is_production and not database_url:
            raise ValueError("TRAMA_DATABASE_URL es obligatorio en produccion")
        values["environment"] = environment
        values["database_url"] = database_url
        values["state_backend"] = "postgres" if database_url else "sqlite"
        values["require_tenant_context"] = _read_bool(
            "TRAMA_REQUIRE_TENANT_CONTEXT",
            values["require_tenant_context"] or is_production,
        )
        values["api_url"] = _read_url(
            "TRAMA_API_URL",
            f"http://{values['api_host']}:{values['api_port']}",
        )
        for name in ("colibri_url", "ollama_url"):
            values[name] = _read_url(env_name(name), values[name])
        values["utopia_mcp_url"] = _read_url(
            env_name("utopia_mcp_url"), values["utopia_mcp_url"], allow_empty=True
        )
        if values["utopia_url"]:
            values["utopia_url"] = _read_url(
                env_name("utopia_url"), values["utopia_url"]
            )
        for name in SECRET_NAMES:
            if values[name]:
                CredentialStore().validate(name, values[name])
        return cls(**values)
