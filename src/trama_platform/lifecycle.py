"""Ciclo de vida seguro del proceso API local de TRAMA."""

from __future__ import annotations

import os
import signal
import subprocess
from pathlib import Path
from typing import Callable, Sequence


def _is_running(pid: int) -> bool:
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def _terminate(pid: int) -> None:
    if os.name == "nt":
        subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            check=True,
            capture_output=True,
            text=True,
        )
        return
    os.kill(pid, signal.SIGTERM)


def _command_line(pid: int) -> str:
    if os.name == "nt":
        completed = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-NonInteractive",
                "-Command",
                f"(Get-CimInstance Win32_Process -Filter 'ProcessId = {pid}').CommandLine",
            ],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return completed.stdout.strip()
    try:
        return Path(f"/proc/{pid}/cmdline").read_bytes().replace(b"\x00", b" ").decode()
    except (FileNotFoundError, OSError, UnicodeDecodeError):
        return ""


def _owns_command(pid: int, command: Sequence[str]) -> bool:
    line = _command_line(pid).casefold()
    return bool(line) and all(part.casefold() in line for part in command[1:])


class GatewaySupervisor:
    """Inicia y detiene únicamente el proceso registrado por TRAMA."""

    def __init__(
        self,
        *,
        state_dir: str | Path,
        command: Sequence[str] = (),
        popen_factory: Callable[..., subprocess.Popen[str]] = subprocess.Popen,
        is_running: Callable[[int], bool] = _is_running,
        is_owned: Callable[[int], bool] | None = None,
        terminate: Callable[[int], None] = _terminate,
    ) -> None:
        self.state_dir = Path(state_dir)
        self.command = list(command)
        self.popen_factory = popen_factory
        self.is_running = is_running
        self.is_owned = is_owned or (lambda pid: _owns_command(pid, self.command))
        self.terminate = terminate

    @property
    def pid_path(self) -> Path:
        return self.state_dir / "trama-api.pid"

    @property
    def log_path(self) -> Path:
        return self.state_dir / "trama-api.log"

    def _read_pid(self) -> int | None:
        try:
            return int(self.pid_path.read_text(encoding="utf-8").strip())
        except (FileNotFoundError, ValueError):
            return None

    def _clear_pid(self) -> None:
        self.pid_path.unlink(missing_ok=True)

    def status(self) -> dict[str, int | str]:
        pid = self._read_pid()
        if pid is not None and self.is_running(pid):
            if not self.is_owned(pid):
                return {"status": "foreign_process", "pid": pid}
            return {"status": "running", "pid": pid}
        if pid is not None:
            self._clear_pid()
        return {"status": "stopped"}

    def start(self) -> dict[str, int | str]:
        current = self.status()
        if current["status"] == "running":
            return {"status": "already_running", "pid": current["pid"]}
        if not self.command:
            raise ValueError("No hay un comando configurado para iniciar el gateway")

        self.state_dir.mkdir(parents=True, exist_ok=True)
        with self.log_path.open("a", encoding="utf-8") as log_file:
            process = self.popen_factory(
                self.command,
                stdin=subprocess.DEVNULL,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                text=True,
                creationflags=getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0),
            )
        self.pid_path.write_text(str(process.pid), encoding="utf-8")
        return {"status": "started", "pid": process.pid}

    def stop(self) -> dict[str, int | str]:
        pid = self._read_pid()
        if pid is None:
            return {"status": "not_running"}
        if self.is_running(pid):
            if self.is_owned(pid):
                self.terminate(pid)
                result: dict[str, int | str] = {"status": "stopped", "pid": pid}
            else:
                result = {"status": "foreign_process", "pid": pid}
        else:
            result = {"status": "stale_pid", "pid": pid}
        self._clear_pid()
        return result
