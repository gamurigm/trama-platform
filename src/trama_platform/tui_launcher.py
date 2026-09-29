"""Launch the sole TypeScript interface and its managed local API."""

import os
import shutil
import subprocess
import sys
import time
from pathlib import Path
from urllib.parse import urlsplit

import httpx

from .lifecycle import GatewaySupervisor


def detect_repository(directory: Path) -> dict[str, str]:
    """Return local Git repository details for the directory that launched the TUI."""
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), "rev-parse", "--show-toplevel"],
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return {}

    root = Path(result.stdout.strip()).resolve()
    details = {"root": str(root)}
    branch = _git_value(root, "branch", "--show-current")
    if branch:
        details["branch"] = branch
    remote = _git_value(root, "remote", "get-url", "origin")
    if remote:
        details["remote"] = _safe_remote(remote)
    return details


def _git_value(directory: Path, *arguments: str) -> str:
    try:
        result = subprocess.run(
            ["git", "-C", str(directory), *arguments],
            capture_output=True,
            check=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return ""
    return result.stdout.strip()


def _safe_remote(remote: str) -> str:
    """Remove credentials from URL style remotes before passing them to the UI."""
    address = urlsplit(remote)
    if address.scheme and address.hostname:
        host = address.hostname
        if address.port:
            host = f"{host}:{address.port}"
        return address._replace(netloc=host).geturl()
    if "@" in remote and ":" in remote.split("@", 1)[1]:
        return remote.split("@", 1)[1]
    return remote


def bun_executable() -> str:
    found = shutil.which("bun.exe") or shutil.which("bun")
    if found and Path(found).suffix.casefold() not in {".cmd", ".bat", ".ps1"}:
        return found
    if found:
        # npm installs a command shim and the executable next to its package.
        executable = Path(found).parent / "node_modules" / "bun" / "bin" / "bun.exe"
        if executable.is_file():
            return str(executable)
    raise RuntimeError("Bun no está disponible. Instálalo y vuelve a ejecutar trama.")


def launch_tui(settings, api_url: str) -> int:
    repository = detect_repository(Path.cwd())
    root = Path(os.getenv("TRAMA_APP_ROOT", Path(__file__).resolve().parents[2])).resolve()
    if not (root / "tui" / "src" / "index.tsx").is_file():
        raise RuntimeError("No se encontró la TUI TypeScript en TRAMA_APP_ROOT")
    bun = bun_executable()
    os.environ["TRAMA_APP_ROOT"] = str(root)
    address = urlsplit(api_url)
    if address.hostname in {"localhost", "127.0.0.1"} and (address.port or 80) == settings.api_port:
        supervisor = GatewaySupervisor(
            state_dir=settings.state_path.parent,
            command=[
                sys.executable,
                "-m",
                "trama_platform",
                "api",
                "--host",
                settings.api_host,
                "--port",
                str(settings.api_port),
            ],
        )
        if supervisor.status()["status"] == "foreign_process":
            raise RuntimeError("El PID registrado pertenece a otro proceso; revisa trama doctor")
        supervisor.start()
        ready = False
        for _ in range(30):
            try:
                response = httpx.get(api_url.rstrip("/") + "/health", timeout=0.5)
                ready = response.is_success and response.json().get("service") == "trama"
            except (httpx.HTTPError, ValueError):
                pass
            if ready:
                break
            time.sleep(0.25)
        if not ready:
            raise RuntimeError("La API no pudo iniciar. Revisa artifacts/state/trama-api.log")
    environment = os.environ.copy()
    environment.update(
        TRAMA_APP_ROOT=str(root),
        TRAMA_PYTHON_EXECUTABLE=sys.executable,
        TRAMA_API_URL=api_url,
        TRAMA_UI_API_TOKEN=settings.api_token or "",
        TRAMA_REPOSITORY_ROOT=repository.get("root", ""),
        TRAMA_REPOSITORY_BRANCH=repository.get("branch", ""),
        TRAMA_REPOSITORY_REMOTE=repository.get("remote", ""),
    )
    return subprocess.run(
        [bun, "run", "--cwd", str(root / "tui"), "start"], cwd=root, env=environment, check=False
    ).returncode
