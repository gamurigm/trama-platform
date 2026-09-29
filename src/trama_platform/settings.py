"""Configuracion tipada de TRAMA desde variables de entorno."""

from __future__ import annotations

import os
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlsplit


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
    api_token: str | None = None
    gateway_url: str | None = None
    gateway_token: str | None = None
    coordination_backend: str = "memory"
    cccc_executable: str = "cccc"
    cccc_timeout_seconds: int = 30
    cccc_bridge_url: str = "http://host.docker.internal:8091"
    cccc_bridge_token: str | None = None
    cccc_bridge_timeout_seconds: int = 35
    cccc_bridge_host: str = "127.0.0.1"
    cccc_bridge_port: int = 8091
    cccc_allowed_actors: str = ""
    cccc_result_recipient: str = "foreman"
    queue_capacity: int = 100
    max_concurrency: int = 4
    dispatch_timeout_seconds: int = 900
    semantica_kg_path: str | None = None
    utopia_url: str | None = None
    utopia_kb_id: str | None = None
    utopia_token: str | None = None
    colibri_url: str | None = None
    colibri_model: str | None = None
    nats_url: str = "nats://127.0.0.1:4222"
    nats_stream: str = "TRAMA_EVENTS"
    nats_subject: str = "trama.task.admitted.v1"
    nats_durable: str = "trama-python-dispatch"
    hermes_executable: str = "hermes"
    hermes_config_path: str = "~/.hermes/config.yaml"

    def __post_init__(self) -> None:
        if self.coordination_backend not in {"memory", "cccc", "cccc-bridge"}:
            raise ValueError(
                "TRAMA_COORDINATION_BACKEND debe ser 'memory', 'cccc' o 'cccc-bridge'"
            )
        try:
            bridge_url = urlsplit(self.cccc_bridge_url)
            _ = bridge_url.port
        except ValueError:
            bridge_url = None
        if (
            bridge_url is None
            or bridge_url.scheme not in {"http", "https"}
            or not bridge_url.hostname
            or bridge_url.username
            or bridge_url.password
            or bridge_url.query
            or bridge_url.fragment
        ):
            raise ValueError("TRAMA_CCCC_BRIDGE_URL debe ser una URL HTTP(S) sin credenciales")

    @property
    def allowed_cccc_actors(self) -> frozenset[str]:
        return frozenset(
            actor.strip() for actor in self.cccc_allowed_actors.split(",") if actor.strip()
        )

    @property
    def state_path(self) -> Path:
        root = Path(self.state_dir)
        if not root.is_absolute() and os.getenv("TRAMA_APP_ROOT"):
            root = Path(os.environ["TRAMA_APP_ROOT"]) / root
        return root / "trama.db"

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
                if isinstance(default, int):
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
        for name in SECRET_NAMES:
            if values[name]:
                CredentialStore().validate(name, values[name])
        return cls(**values)
