"""Configuration routes, intentionally separate from domain state endpoints."""

import os
import shutil
from pathlib import Path

from fastapi import HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, SecretStr

from .credential_store import CredentialStore
from .hermes import HermesAdapter
from .integration_status import check_all, check_integration, run_command, tool_inventory
from .settings import TramaSettings
from .user_config import UserConfigStore, config_snapshot


class ConfigUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    values: dict[str, str | int | None] = Field(max_length=50)


class SecretUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    value: SecretStr = Field(min_length=1, max_length=2000)


def register_config_routes(app, active: TramaSettings, store=None, vault=None):
    store = store or UserConfigStore()
    vault = vault or CredentialStore()

    def fresh():
        return TramaSettings.from_env(store=store, vault=vault)

    def guard(request: Request):
        # Browser pages must not drive local executable/configuration endpoints.
        if request.headers.get("origin"):
            raise HTTPException(403, "Operación disponible desde la consola local")

    def translate(action):
        try:
            return action()
        except ValueError as exc:
            raise HTTPException(400, str(exc)) from None
        except (RuntimeError, OSError):
            raise HTTPException(
                503, "No se pudo acceder a la configuración o al almacén seguro"
            ) from None

    @app.get("/v1/config")
    def get_config():
        return translate(lambda: config_snapshot(active, store, vault))

    @app.put("/v1/config")
    def save_config(payload: ConfigUpdate, request: Request):
        guard(request)
        translate(lambda: store.update(payload.values))
        return get_config()

    @app.get("/v1/config/secrets")
    def list_secrets():
        return get_config()["secrets"]

    @app.put("/v1/config/secrets/{name}")
    def save_secret(name: str, payload: SecretUpdate, request: Request):
        guard(request)
        translate(lambda: vault.set(name, payload.value.get_secret_value()))
        return {"name": name, "configured": True}

    @app.delete("/v1/config/secrets/{name}")
    def delete_secret(name: str, request: Request):
        guard(request)
        translate(lambda: vault.delete(name))
        return {"name": name, "configured": False}

    @app.get("/v1/integrations")
    def integrations():
        return {"integrations": translate(lambda: check_all(fresh())), "tools": tool_inventory()}

    @app.post("/v1/integrations/{name}/check")
    def check(name: str):
        return translate(lambda: check_integration(name, fresh()))

    @app.post("/v1/integrations/cccc/{action}")
    def daemon(action: str, request: Request):
        guard(request)
        if action not in {"start", "stop"}:
            raise HTTPException(404, "Acción desconocida")
        executable = shutil.which(fresh().cccc_executable)
        if not executable:
            raise HTTPException(409, "CCCC no está instalado")
        try:
            completed = run_command([executable, "daemon", action])
        except Exception:
            raise HTTPException(503, "No se pudo cambiar el estado de CCCC") from None
        if completed.returncode:
            raise HTTPException(409, "CCCC no pudo completar la operación")
        return check("cccc")

    @app.post("/v1/integrations/hermes/configure")
    def configure_hermes(request: Request):
        guard(request)
        configured = fresh()
        root = Path(os.getenv("TRAMA_APP_ROOT", Path(__file__).resolve().parents[2]))
        translate(
            lambda: HermesAdapter(configured.hermes_executable, cwd=root).write_config(
                Path(configured.hermes_config_path).expanduser(),
                configured.api_url,
                settings=configured,
                include_native_services=True,
            )
        )
        return check("hermes")
