"""Bounded, read-only checks; configured is never a synonym for connected."""

import ast
import importlib.util
import shutil
import socket
import subprocess
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urlsplit

import httpx
import yaml

IDS = ("cccc", "hermes", "mcp", "semantica", "utopia", "colibri", "gateway", "nats", "models")


def tool_inventory() -> list[str]:
    tree = ast.parse(Path(__file__).with_name("mcp_server.py").read_text(encoding="utf-8"))
    return [
        node.name
        for node in ast.walk(tree)
        if isinstance(node, ast.FunctionDef) and node.name.startswith("trama_")
    ]


def run_command(args: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        timeout=5,
        check=False,
        creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
    )


def check_integration(name: str, settings) -> dict:
    if name not in IDS:
        raise ValueError("Integración desconocida")
    result = {
        "id": name,
        "label": name.upper() if name in {"cccc", "mcp", "nats"} else name.title(),
        "status": "not_configured",
        "configured": False,
        "detail": "Sin configurar",
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "tools": [],
    }

    def state(status: str, detail: str, configured=True):
        result.update(status=status, detail=detail, configured=configured)
        return result

    try:
        if name == "mcp":
            result["tools"] = tool_inventory()
            return state(
                "available",
                "Servidor local listo para ofrecer herramientas por stdio; "
                "no implica una sesión cliente activa.",
            )
        if name == "models":
            return state(
                "not_implemented",
                "El control plane aún no tiene un gateway de modelos activo",
                False,
            )
        if name in {"cccc", "hermes"}:
            if name == "cccc" and settings.coordination_backend == "cccc-bridge":
                with httpx.Client(timeout=3, follow_redirects=False) as client:
                    response = client.get(settings.cccc_bridge_url.rstrip("/") + "/healthz")
                payload = response.json() if response.is_success else {}
                healthy = response.is_success and payload.get("status") == "ok"
                return state(
                    "available" if healthy else "unreachable",
                    "Puente CCCC responde; estado de CCCC y ejecución del modelo sin verificar"
                    if healthy
                    else f"Puente CCCC sin respuesta válida (HTTP {response.status_code})",
                )
            executable = shutil.which(getattr(settings, name + "_executable"))
            if name == "hermes":
                path = Path(settings.hermes_config_path).expanduser()
                data = yaml.safe_load(path.read_text(encoding="utf-8")) if path.is_file() else {}
                entry = (data or {}).get("mcp_servers", {}).get("trama", {})
                result["tools"] = entry.get("tools", {}).get("include", [])
                result["configured"] = bool(entry)
            if not executable:
                return state(
                    "not_installed",
                    "Ejecutable no encontrado; puedes preparar su configuración",
                    result["configured"],
                )
            if name == "cccc":
                version = run_command([executable, "--version"])
                daemon = run_command([executable, "daemon", "status"])
                # Never echo arbitrary process output: it may contain local credentials.
                import re

                match = re.search(r"\d+\.\d+\.\d+", version.stdout or "")
                release = match.group(0) if match else "versión no disponible"
                active = daemon.returncode == 0
                linked = settings.coordination_backend == "cccc"
                return state(
                    "connected" if active and linked else "available" if active else "stopped",
                    f"{release} · daemon {'activo' if active else 'detenido'}"
                    f" · backend TRAMA {settings.coordination_backend}",
                    linked,
                )
            return state(
                "stopped" if result["configured"] else "not_configured",
                "Instalado; entrada MCP preparada. La sesión de Hermes no se comprueba."
                if result["configured"]
                else "Instalado; falta la entrada MCP de TRAMA",
                result["configured"],
            )
        if name == "semantica":
            if not settings.semantica_kg_path:
                return result
            if importlib.util.find_spec("semantica") is None:
                return state("not_installed", "Paquete Semantica no instalado")
            return state(
                "connected"
                if Path(settings.semantica_kg_path).expanduser().exists()
                else "unreachable",
                "Comprobación local del paquete y ruta; no valida el contenido del grafo",
            )
        if name == "nats":
            if not settings.nats_url:
                return result
            address = urlsplit(settings.nats_url)
            with socket.create_connection(
                (address.hostname, address.port or 4222), timeout=2
            ) as connection:
                connection.settimeout(2)
                greeting = connection.recv(1024)
            return state(
                "connected" if greeting.startswith(b"INFO ") else "unreachable",
                "Servidor NATS responde; autenticación y consumidor no comprobados",
            )
        url = getattr(settings, name + "_url")
        if not url:
            return result
        token = getattr(settings, name + "_token", None)
        with httpx.Client(
            timeout=3,
            follow_redirects=False,
            headers={"Authorization": f"Bearer {token}"} if token else {},
        ) as client:
            if name == "utopia":
                if not settings.utopia_kb_id or not token:
                    return state(
                        "not_configured", "Falta el ID de base de conocimiento o su token", False
                    )
                response = client.post(
                    url.rstrip("/") + f"/api/v1/kbs/{quote(settings.utopia_kb_id, safe='')}/mcp",
                    json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
                )
                payload = response.json() if response.is_success else {}
                healthy = response.is_success and isinstance(
                    payload.get("result", {}).get("tools"), list
                )
            else:
                response = client.get(
                    url.rstrip("/") + ("/v1/models" if name == "colibri" else "/health")
                )
                payload = response.json() if response.is_success else {}
                healthy = response.is_success and (
                    isinstance(payload.get("data"), list)
                    if name == "colibri"
                    else payload.get("status") in {"ok", "ready", "healthy"}
                )
            return state(
                "connected" if healthy else "unreachable",
                "Respuesta de servicio válida"
                if healthy
                else f"Sin respuesta válida del servicio (HTTP {response.status_code})",
            )
    except (
        OSError,
        ValueError,
        TypeError,
        AttributeError,
        httpx.HTTPError,
        subprocess.SubprocessError,
        yaml.YAMLError,
    ):
        return state("unreachable", "No se pudo completar la comprobación; revisa la configuración")


def check_all(settings) -> list[dict]:
    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(lambda name: check_integration(name, settings), IDS))
