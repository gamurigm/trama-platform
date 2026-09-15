"""Persistencia local del control plane de TRAMA."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator, TypeVar

from pydantic import BaseModel

from .contracts import (
    AgentResult,
    MemoryCandidate,
    OperationEvent,
    ProjectManifest,
    PromotionRequest,
    TaskEnvelope,
)

ModelT = TypeVar("ModelT", bound=BaseModel)


class SqliteStateStore:
    """Guarda estado de TRAMA sin introducir dependencias en los proyectos."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            connection.execute("PRAGMA foreign_keys = ON")
            yield connection
            connection.commit()
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS schema_migrations (
                    version INTEGER PRIMARY KEY,
                    applied_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS state_records (
                    kind TEXT NOT NULL,
                    record_id TEXT NOT NULL,
                    payload TEXT NOT NULL,
                    PRIMARY KEY (kind, record_id)
                )
                """
            )
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS operation_events (
                    event_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)"
            )

    def _save_model(self, kind: str, record_id: str, model: BaseModel) -> None:
        payload = json.dumps(model.model_dump(mode="json"), ensure_ascii=False)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO state_records(kind, record_id, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(kind, record_id) DO UPDATE SET payload = excluded.payload
                """,
                (kind, record_id, payload),
            )

    def _load_models(self, kind: str, model_type: type[ModelT]) -> list[ModelT]:
        with self._connection() as connection:
            rows = connection.execute(
                "SELECT payload FROM state_records WHERE kind = ? ORDER BY record_id",
                (kind,),
            ).fetchall()
        return [model_type.model_validate(json.loads(row["payload"])) for row in rows]

    def save_project(self, project: ProjectManifest) -> None:
        self._save_model("project", project.project_id, project)

    def load_projects(self) -> list[ProjectManifest]:
        return self._load_models("project", ProjectManifest)

    def save_task(self, task: TaskEnvelope) -> None:
        self._save_model("task", task.task_id, task)

    def load_tasks(self) -> list[TaskEnvelope]:
        return self._load_models("task", TaskEnvelope)

    def save_result(self, result: AgentResult) -> None:
        self._save_model("result", result.task_id, result)

    def load_results(self) -> list[AgentResult]:
        return self._load_models("result", AgentResult)

    def save_candidate(self, candidate: MemoryCandidate) -> None:
        self._save_model("candidate", candidate.candidate_id, candidate)

    def load_candidates(self) -> list[MemoryCandidate]:
        return self._load_models("candidate", MemoryCandidate)

    def save_promotion(self, promotion: PromotionRequest) -> None:
        self._save_model("promotion", promotion.promotion_id, promotion)

    def load_promotions(self) -> list[PromotionRequest]:
        return self._load_models("promotion", PromotionRequest)

    def append_event(self, event: OperationEvent) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO operation_events(event_id, created_at, payload)
                VALUES (?, ?, ?)
                """,
                (
                    event.event_id,
                    event.created_at.isoformat(),
                    json.dumps(event.model_dump(mode="json"), ensure_ascii=False),
                ),
            )

    def list_events(self, limit: int = 100) -> list[OperationEvent]:
        bounded_limit = max(1, min(limit, 1000))
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM operation_events
                ORDER BY rowid DESC LIMIT ?
                """,
                (bounded_limit,),
            ).fetchall()
        return [
            OperationEvent.model_validate(json.loads(row["payload"]))
            for row in reversed(rows)
        ]

    def count(self, kind: str) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM state_records WHERE kind = ?",
                (kind,),
            ).fetchone()
        return int(row["total"])

    def count_events(self) -> int:
        with self._connection() as connection:
            row = connection.execute("SELECT COUNT(*) AS total FROM operation_events").fetchone()
        return int(row["total"])
