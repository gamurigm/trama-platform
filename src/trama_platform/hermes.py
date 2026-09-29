"""Adaptador de proceso para Hermes Agent."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Any, Sequence

import yaml


class HermesAdapter:
    """Integra Hermes por CLI y configuración, sin depender de sus módulos internos."""

    TRAMA_TOOLS = [
        "trama_register_project",
        "trama_register_requirement",
        "trama_register_phase",
        "trama_search_context",
        "trama_submit_task",
        "trama_get_overview",
        "trama_record_result",
        "trama_capture_memory",
    ]

    def __init__(self, executable: str = "hermes", *, cwd: str | Path | None = None) -> None:
        self.executable = executable
        self.cwd = Path(cwd) if cwd is not None else None

    def check(self) -> dict[str, str]:
        resolved = shutil.which(self.executable)
        if resolved is None:
            return {"status": "missing", "executable": self.executable}
        try:
            completed = subprocess.run(
                [resolved, "--version"],
                cwd=self.cwd,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.TimeoutExpired) as exc:
            return {"status": "error", "executable": resolved, "message": str(exc)}
        version = (completed.stdout or completed.stderr).strip()
        return {
            "status": "ready" if completed.returncode == 0 else "error",
            "executable": resolved,
            "version": version,
        }

    def render_config(self, api_url: str) -> dict[str, Any]:
        return {
            "approvals": {
                "mode": "manual",
                "timeout": 300,
                "cron_mode": "deny",
                "single_query_mode": "deny",
                "unattended_mode": "deny",
            },
            "mcp_servers": {
                "trama": {
                    "command": "uv",
                    "args": [
                        "run",
                        "--project",
                        str((self.cwd or Path(__file__).resolve().parents[2]).resolve()),
                        "--directory",
                        str((self.cwd or Path(__file__).resolve().parents[2]).resolve()),
                        "trama",
                        "mcp",
                        "--api-url",
                        api_url,
                    ],
                    "timeout": 30,
                    "connect_timeout": 10,
                    "tools": {
                        "include": self.TRAMA_TOOLS,
                        "resources": False,
                        "prompts": False,
                    },
                }
            },
        }

    def write_config(self, path: str | Path, api_url: str) -> Path:
        output = Path(path).expanduser()
        try:
            existing = yaml.safe_load(output.read_text(encoding="utf-8")) if output.exists() else {}
            existing = existing or {}
            if not isinstance(existing, dict):
                raise ValueError
            generated = self.render_config(api_url)
            servers = existing.setdefault("mcp_servers", {})
            approvals = existing.setdefault("approvals", {})
            if not isinstance(servers, dict) or not isinstance(approvals, dict):
                raise ValueError
            servers["trama"] = generated["mcp_servers"]["trama"]
            approvals.update(generated["approvals"])
        except (ValueError, yaml.YAMLError):
            raise ValueError("Configuración Hermes no válida; no se modificó el archivo") from None
        output.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(dir=output.parent, suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                yaml.safe_dump(existing, stream, sort_keys=False, allow_unicode=True)
            os.replace(temporary, output)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return output

    def launch(self, extra_args: Sequence[str] = ()) -> subprocess.Popen[str]:
        resolved = shutil.which(self.executable) or self.executable
        return subprocess.Popen(
            [resolved, *extra_args],
            cwd=self.cwd,
            text=True,
        )

    def run(self, extra_args: Sequence[str] = ()) -> int:
        process = self.launch(extra_args)
        return process.wait()
