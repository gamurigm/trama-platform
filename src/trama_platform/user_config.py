"""Validated non-secret configuration, saved atomically outside the repository."""

import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from threading import RLock
from urllib.parse import urlsplit

from .credential_store import SECRET_NAMES, CredentialStore

LOCK = RLock()
READ_ONLY = {"api_host", "api_port", "api_url", "state_dir"}
ENV_NAMES = {"environment": "TRAMA_ENV"}


def env_name(name: str) -> str:
    return ENV_NAMES.get(name, "TRAMA_" + name.upper())


def safe_value(name: str, value):
    if name.endswith("_url") and value:
        try:
            parsed = urlsplit(value)
            if parsed.username or parsed.password or parsed.query or parsed.fragment:
                return f"{parsed.scheme}://{parsed.hostname or ''}" + (
                    f":{parsed.port}" if parsed.port else ""
                )
        except ValueError:
            return "[URL no válida]"
    return value


class UserConfigStore:
    def __init__(self, path: Path | None = None):
        self.path = (
            path
            or Path(os.getenv("LOCALAPPDATA", str(Path.home() / ".config")))
            / "TRAMA"
            / "config.json"
        )

    def validate(self, values: dict) -> dict:
        from .settings import TramaSettings

        defaults = asdict(TramaSettings())
        for name, value in values.items():
            if name not in defaults or name in SECRET_NAMES or name in READ_ONLY:
                raise ValueError("Parámetro desconocido o de solo lectura")
            if value is None:
                continue
            if isinstance(defaults[name], int):
                if type(value) is not int or not 1 <= value <= 1_000_000:
                    raise ValueError(f"{name}: se requiere un entero positivo")
            elif not isinstance(value, str) or not value.strip() or len(value) > 2000:
                raise ValueError(f"{name}: texto no válido")
            if name == "coordination_backend" and value not in {
                "memory",
                "cccc",
                "cccc-bridge",
            }:
                raise ValueError("Coordinador: selecciona memory, cccc o cccc-bridge")
            if name.endswith("_url"):
                try:
                    parsed = urlsplit(value)
                    allowed = {"nats", "tls"} if name == "nats_url" else {"http", "https"}
                    valid = (
                        parsed.scheme in allowed
                        and parsed.hostname
                        and not (
                            parsed.username or parsed.password or parsed.query or parsed.fragment
                        )
                    )
                    _ = parsed.port
                except ValueError:
                    valid = False
                if not valid:
                    raise ValueError(
                        f"{name}: URL sin credenciales, consulta ni fragmento requerida"
                    )
        return values

    def read(self) -> dict:
        with LOCK:
            try:
                values = json.loads(self.path.read_text(encoding="utf-8"))
                if not isinstance(values, dict):
                    raise ValueError
                return self.validate(values)
            except FileNotFoundError:
                return {}
            except (ValueError, OSError):
                raise ValueError("El archivo de configuración de TRAMA no es válido") from None

    def update(self, values: dict) -> dict:
        self.validate(values)
        with LOCK:
            merged = self.read()
            for name, value in values.items():
                if value is None:
                    merged.pop(name, None)
                else:
                    merged[name] = value
            self.path.parent.mkdir(parents=True, exist_ok=True)
            fd, temporary = tempfile.mkstemp(dir=self.path.parent, suffix=".tmp")
            try:
                with os.fdopen(fd, "w", encoding="utf-8") as output:
                    json.dump(merged, output, ensure_ascii=False, indent=2)
                    output.write("\n")
                os.replace(temporary, self.path)
            finally:
                Path(temporary).unlink(missing_ok=True)
            return merged


def config_snapshot(active, store=None, vault=None) -> dict:
    from .settings import TramaSettings

    store = store or UserConfigStore()
    vault = vault or CredentialStore()
    saved = store.read()
    effective = TramaSettings.from_env(store=store, vault=vault)
    current = asdict(active)
    items = []
    for name, value in asdict(effective).items():
        if name in SECRET_NAMES:
            continue
        items.append(
            {
                "name": name,
                "value": safe_value(name, value),
                "active_value": safe_value(name, current[name]),
                "source": "environment"
                if env_name(name) in os.environ
                else "user"
                if name in saved
                else "default",
                "read_only": name in READ_ONLY,
                "restart_required": value != current[name],
            }
        )
    secrets = [
        {
            "name": name,
            "configured": bool(getattr(effective, name)),
            "source": "environment"
            if os.getenv(env_name(name))
            else "vault"
            if vault.has(name)
            else "default",
            "restart_required": getattr(effective, name) != current[name],
        }
        for name in sorted(SECRET_NAMES)
    ]
    return {
        "settings": items,
        "secrets": secrets,
        "restart_required": any(x["restart_required"] for x in items + secrets),
    }
