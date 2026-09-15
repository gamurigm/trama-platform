"""Adaptador de proceso para Hermes Agent."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path
from typing import Any, Sequence

import yaml

from .settings import TramaSettings


class HermesAdapter:
    """Integra Hermes por CLI y configuración, sin depender de sus módulos internos."""

    TRAMA_TOOLS = [
        "trama_register_project",
        "trama_search_context",
        "trama_submit_task",
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

    @staticmethod
    def _openai_base_url(service_url: str) -> str:
        normalized = service_url.rstrip("/")
        return normalized if normalized.endswith("/v1") else f"{normalized}/v1"

    def render_config(
        self,
        api_url: str,
        *,
        settings: TramaSettings | None = None,
        include_native_services: bool = False,
    ) -> dict[str, Any]:
        profile = settings or TramaSettings()
        ollama_base_url = self._openai_base_url(profile.ollama_url)
        colibri_base_url = self._openai_base_url(profile.colibri_url)
        config: dict[str, Any] = {
            "approvals": {
                "mode": "manual",
                "timeout": 300,
                "cron_mode": "deny",
                "single_query_mode": "deny",
                "unattended_mode": "deny",
            },
            "model": {
                "default": profile.ollama_model,
                "provider": "custom",
                "base_url": ollama_base_url,
                "api_key": "local",
            },
            "custom_providers": [
                {
                    "name": "ollama",
                    "base_url": ollama_base_url,
                    "api_key": "local",
                    "models": [profile.ollama_model],
                },
                {
                    "name": "colibri",
                    "base_url": colibri_base_url,
                    "api_key": "local",
                    "models": [profile.colibri_model],
                },
            ],
            "mcp_servers": {
                "trama": {
                    "command": "uv",
                    "args": [
                        "run",
                        "--project",
                        ".",
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
        if include_native_services:
            if profile.semantica_enabled:
                config["mcp_servers"]["semantica"] = {
                    "type": "stdio",
                    "command": profile.semantica_executable,
                    "args": [],
                }
            if profile.utopia_mcp_url:
                config["mcp_servers"]["utopia"] = {
                    "type": "streamable-http",
                    "url": profile.utopia_mcp_url,
                    "headers": {"Authorization": "Bearer ${UTOPIA_API_TOKEN}"},
                }
        return config

    def write_config(
        self,
        path: str | Path,
        api_url: str,
        *,
        settings: TramaSettings | None = None,
        include_native_services: bool = False,
    ) -> Path:
        output = Path(path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(
            yaml.safe_dump(
                self.render_config(
                    api_url,
                    settings=settings,
                    include_native_services=include_native_services,
                ),
                sort_keys=False,
                allow_unicode=True,
            ),
            encoding="utf-8",
        )
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
