"""Adaptadores externos pequeños y verificables."""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass

from .contracts import AgentResult, TaskEnvelope
from .ports import CoordinationPort


@dataclass
class CcccCliAdapter(CoordinationPort):
    executable: str = "cccc"
    cwd: str | None = None
    timeout_seconds: int = 30
    result_recipient: str = "foreman"

    def _run(self, args: list[str]) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.executable, *args],
            cwd=self.cwd,
            check=True,
            capture_output=True,
            text=True,
            timeout=self.timeout_seconds,
        )

    def submit_task(self, task: TaskEnvelope) -> str:
        message = json.dumps(task.model_dump(mode="json"), ensure_ascii=False)
        result = self._run(
            [
                "tracked-send",
                message,
                "--to",
                task.actor,
                "--title",
                task.task_id,
                "--idempotency-key",
                task.task_id,
                "--outcome",
                "Devolver AgentResult con pruebas y evidencia",
            ]
        )
        return result.stdout.strip() or task.task_id

    def record_result(self, result: AgentResult) -> None:
        message = json.dumps(result.model_dump(mode="json"), ensure_ascii=False)
        self._run(["send", message, "--to", self.result_recipient])
