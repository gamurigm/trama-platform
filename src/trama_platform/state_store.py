"""Persistencia local del control plane de TRAMA."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path
from time import time
from typing import Any, Iterator, Literal, TypeVar

from pydantic import BaseModel

from .contracts import (
    AgentResult,
    LogLevel,
    MemoryCandidate,
    OperationEvent,
    PlanProposal,
    ProjectManifest,
    ProjectPhase,
    PromotionRequest,
    Requirement,
    TaskEnvelope,
    TaskLog,
)
from .observability import sanitize_message

ModelT = TypeVar("ModelT", bound=BaseModel)
InboxDecision = Literal["claimed", "duplicate", "in_flight"]


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
                """
                CREATE TABLE IF NOT EXISTS task_logs (
                    log_id TEXT PRIMARY KEY,
                    created_at TEXT NOT NULL,
                    organization_id TEXT NOT NULL,
                    project_id TEXT NOT NULL,
                    requirement_id TEXT,
                    phase_id TEXT,
                    task_id TEXT,
                    level TEXT NOT NULL,
                    sequence INTEGER NOT NULL,
                    payload TEXT NOT NULL
                )
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_logs_project
                ON task_logs(organization_id, project_id)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_logs_task
                ON task_logs(task_id, created_at, sequence)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_logs_phase
                ON task_logs(phase_id, created_at, sequence)
                """
            )
            connection.execute(
                """
                CREATE INDEX IF NOT EXISTS idx_task_logs_requirement
                ON task_logs(requirement_id, created_at, sequence)
                """
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (1)"
            )
            connection.execute(
                "INSERT OR IGNORE INTO schema_migrations(version) VALUES (2)"
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

    def save_requirement(self, requirement: Requirement) -> None:
        self._save_model("requirement", requirement.requirement_id, requirement)

    def load_requirements(self) -> list[Requirement]:
        return self._load_models("requirement", Requirement)

    def save_plan_proposal(self, proposal: PlanProposal) -> None:
        self._save_model("plan_proposal", proposal.proposal_id, proposal)

    def load_plan_proposals(self) -> list[PlanProposal]:
        return self._load_models("plan_proposal", PlanProposal)

    def save_phase(self, phase: ProjectPhase) -> None:
        self._save_model("phase", phase.phase_id, phase)

    def load_phases(self) -> list[ProjectPhase]:
        return self._load_models("phase", ProjectPhase)

    def save_task(self, task: TaskEnvelope) -> None:
        self._save_model("task", task.task_id, task)

    def load_tasks(self) -> list[TaskEnvelope]:
        return self._load_models("task", TaskEnvelope)

    def save_task_transition(self, task: TaskEnvelope, event: OperationEvent) -> None:
        task_payload = json.dumps(task.model_dump(mode="json"), ensure_ascii=False)
        event_payload = json.dumps(event.model_dump(mode="json"), ensure_ascii=False)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO state_records(kind, record_id, payload)
                VALUES (?, ?, ?)
                ON CONFLICT(kind, record_id) DO UPDATE SET payload = excluded.payload
                """,
                ("task", task.task_id, task_payload),
            )
            connection.execute(
                """
                INSERT INTO operation_events(event_id, created_at, payload)
                VALUES (?, ?, ?)
                """,
                (
                    event.event_id,
                    event.created_at.isoformat(),
                    event_payload,
                ),
            )

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

    def append_task_log(self, log: TaskLog) -> None:
        message, metadata = sanitize_message(log.message, log.metadata)
        safe_log = log.model_copy(update={"message": message, "metadata": metadata})
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR IGNORE INTO task_logs(
                    log_id, created_at, organization_id, project_id,
                    requirement_id, phase_id, task_id, level, sequence, payload
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    safe_log.log_id,
                    safe_log.created_at.isoformat(),
                    safe_log.organization_id,
                    safe_log.project_id,
                    safe_log.requirement_id,
                    safe_log.phase_id,
                    safe_log.task_id,
                    safe_log.level,
                    safe_log.sequence,
                    json.dumps(safe_log.model_dump(mode="json"), ensure_ascii=False),
                ),
            )

    @staticmethod
    def _task_log_filters(
        *,
        organization_id: str | None,
        project_id: str | None,
        task_id: str | None,
        phase_id: str | None,
        requirement_id: str | None,
        level: LogLevel | None,
    ) -> tuple[str, list[str]]:
        clauses = ["1 = 1"]
        values: list[str] = []
        for column, value in (
            ("organization_id", organization_id),
            ("project_id", project_id),
            ("task_id", task_id),
            ("phase_id", phase_id),
            ("requirement_id", requirement_id),
            ("level", level),
        ):
            if value is not None:
                clauses.append(f"{column} = ?")
                values.append(value)
        return " AND ".join(clauses), values

    def list_task_logs(
        self,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        phase_id: str | None = None,
        requirement_id: str | None = None,
        level: LogLevel | None = None,
        limit: int = 100,
    ) -> list[TaskLog]:
        bounded_limit = max(1, min(limit, 1000))
        where, values = self._task_log_filters(
            organization_id=organization_id,
            project_id=project_id,
            task_id=task_id,
            phase_id=phase_id,
            requirement_id=requirement_id,
            level=level,
        )
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT payload FROM task_logs WHERE {where} "
                "ORDER BY created_at ASC, sequence ASC, rowid ASC LIMIT ?",
                [*values, bounded_limit],
            ).fetchall()
        return [TaskLog.model_validate(json.loads(row["payload"])) for row in rows]

    def count_task_logs(
        self,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        phase_id: str | None = None,
        requirement_id: str | None = None,
        level: LogLevel | None = None,
    ) -> int:
        where, values = self._task_log_filters(
            organization_id=organization_id,
            project_id=project_id,
            task_id=task_id,
            phase_id=phase_id,
            requirement_id=requirement_id,
            level=level,
        )
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS total FROM task_logs WHERE {where}", values
            ).fetchone()
        return int(row["total"])

    def prune_task_logs(self, organization_id: str, project_id: str, max_rows: int) -> int:
        if max_rows < 0:
            raise ValueError("max_rows debe ser no negativo")
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT log_id FROM task_logs
                WHERE organization_id = ? AND project_id = ?
                ORDER BY created_at DESC, sequence DESC, rowid DESC
                LIMIT -1 OFFSET ?
                """,
                (organization_id, project_id, max_rows),
            ).fetchall()
            if not rows:
                return 0
            cursor = connection.executemany(
                "DELETE FROM task_logs WHERE log_id = ?",
                [(row["log_id"],) for row in rows],
            )
        return int(cursor.rowcount)

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

    def ping(self) -> None:
        with self._connection() as connection:
            connection.execute("SELECT 1")


class PostgresStateStore:
    """Fuente de verdad compartida para el control plane distribuido.

    Cada operación toma una conexión independiente para que el adaptador sea
    seguro cuando FastAPI y varios workers lo usan simultáneamente. El schema
    se crea de forma idempotente para que el servicio pueda arrancar después
    de un despliegue; la migración versionada del repositorio sigue siendo el
    mecanismo recomendado para operar cambios de esquema.
    """

    schema = "trama"

    def __init__(self, database_url: str) -> None:
        if not database_url:
            raise ValueError("database_url es obligatorio para PostgresStateStore")
        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as exc:  # pragma: no cover - dependency is packaged
            raise RuntimeError(
                "PostgresStateStore requiere la dependencia psycopg"
            ) from exc
        self.database_url = database_url
        self._psycopg = psycopg
        self._dict_row = dict_row
        self._initialize()

    @contextmanager
    def _connection(self):
        connection = self._psycopg.connect(
            self.database_url,
            row_factory=self._dict_row,
        )
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        statements = (
            "CREATE SCHEMA IF NOT EXISTS trama",
            """
            CREATE TABLE IF NOT EXISTS trama.schema_migrations (
                version INTEGER PRIMARY KEY,
                applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS trama.state_records (
                kind TEXT NOT NULL,
                record_id TEXT NOT NULL,
                organization_id TEXT NOT NULL,
                project_id TEXT,
                payload JSONB NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (kind, organization_id, record_id)
            )
            """,
            """
            DO $$
            BEGIN
                IF EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conrelid = 'trama.state_records'::regclass
                      AND conname = 'state_records_pkey'
                ) THEN
                    ALTER TABLE trama.state_records DROP CONSTRAINT state_records_pkey;
                END IF;
                IF NOT EXISTS (
                    SELECT 1
                    FROM pg_constraint
                    WHERE conrelid = 'trama.state_records'::regclass
                      AND conname = 'state_records_namespace_pkey'
                ) THEN
                    ALTER TABLE trama.state_records
                        ADD CONSTRAINT state_records_namespace_pkey
                        PRIMARY KEY (kind, organization_id, record_id);
                END IF;
            END $$
            """,
            """
            CREATE INDEX IF NOT EXISTS state_records_namespace_idx
            ON trama.state_records (organization_id, project_id, kind)
            """,
            """
            CREATE TABLE IF NOT EXISTS trama.operation_events (
                event_id TEXT PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL,
                organization_id TEXT NOT NULL,
                project_id TEXT,
                payload JSONB NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS operation_events_namespace_idx
            ON trama.operation_events (organization_id, project_id, created_at)
            """,
            """
            CREATE TABLE IF NOT EXISTS trama.task_logs (
                log_id TEXT PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL,
                organization_id TEXT NOT NULL,
                project_id TEXT NOT NULL,
                requirement_id TEXT,
                phase_id TEXT,
                task_id TEXT,
                level TEXT NOT NULL,
                sequence BIGINT NOT NULL,
                payload JSONB NOT NULL
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS task_logs_project_idx
            ON trama.task_logs (organization_id, project_id, created_at, sequence)
            """,
            """
            CREATE INDEX IF NOT EXISTS task_logs_task_idx
            ON trama.task_logs (organization_id, project_id, task_id, created_at, sequence)
            """,
            """
            CREATE TABLE IF NOT EXISTS trama.consumed_events (
                event_id TEXT PRIMARY KEY,
                claimed_until TIMESTAMPTZ NOT NULL,
                completed BOOLEAN NOT NULL DEFAULT FALSE
            )
            """,
        )
        with self._connection() as connection:
            for statement in statements:
                connection.execute(statement)
            connection.execute(
                "INSERT INTO trama.schema_migrations(version) VALUES (1) ON CONFLICT DO NOTHING"
            )

    def ping(self) -> None:
        with self._connection() as connection:
            connection.execute("SELECT 1")

    @staticmethod
    def _payload(row: dict[str, Any]) -> dict[str, Any]:
        payload = row["payload"]
        if isinstance(payload, str):
            return json.loads(payload)
        return payload

    @staticmethod
    def _namespace(model: BaseModel) -> tuple[str, str | None]:
        payload = model.model_dump(mode="json")
        return str(payload.get("organization_id", "default")), payload.get("project_id")

    def _save_model(self, kind: str, record_id: str, model: BaseModel) -> None:
        payload = model.model_dump(mode="json")
        organization_id, project_id = self._namespace(model)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO trama.state_records(
                    kind, record_id, organization_id, project_id, payload, updated_at
                ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT(kind, organization_id, record_id) DO UPDATE SET
                    organization_id = excluded.organization_id,
                    project_id = excluded.project_id,
                    payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (kind, record_id, organization_id, project_id, json.dumps(payload)),
            )

    def _load_models(self, kind: str, model_type: type[ModelT]) -> list[ModelT]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM trama.state_records
                WHERE kind = %s
                ORDER BY record_id
                """,
                (kind,),
            ).fetchall()
        return [model_type.model_validate(self._payload(row)) for row in rows]

    def save_project(self, project: ProjectManifest) -> None:
        self._save_model("project", project.project_id, project)

    def load_projects(self) -> list[ProjectManifest]:
        return self._load_models("project", ProjectManifest)

    def save_requirement(self, requirement: Requirement) -> None:
        self._save_model("requirement", requirement.requirement_id, requirement)

    def load_requirements(self) -> list[Requirement]:
        return self._load_models("requirement", Requirement)

    def save_plan_proposal(self, proposal: PlanProposal) -> None:
        self._save_model("plan_proposal", proposal.proposal_id, proposal)

    def load_plan_proposals(self) -> list[PlanProposal]:
        return self._load_models("plan_proposal", PlanProposal)

    def save_phase(self, phase: ProjectPhase) -> None:
        self._save_model("phase", phase.phase_id, phase)

    def load_phases(self) -> list[ProjectPhase]:
        return self._load_models("phase", ProjectPhase)

    def save_task(self, task: TaskEnvelope) -> None:
        self._save_model("task", task.task_id, task)

    def load_tasks(self) -> list[TaskEnvelope]:
        return self._load_models("task", TaskEnvelope)

    def save_task_transition(self, task: TaskEnvelope, event: OperationEvent) -> None:
        task_payload = task.model_dump(mode="json")
        event_payload = event.model_dump(mode="json")
        organization_id, project_id = self._namespace(task)
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO trama.state_records(
                    kind, record_id, organization_id, project_id, payload, updated_at
                ) VALUES (%s, %s, %s, %s, %s, CURRENT_TIMESTAMP)
                ON CONFLICT(kind, organization_id, record_id) DO UPDATE SET
                    payload = excluded.payload,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    "task",
                    task.task_id,
                    organization_id,
                    project_id,
                    json.dumps(task_payload),
                ),
            )
            connection.execute(
                """
                INSERT INTO trama.operation_events(
                    event_id, created_at, organization_id, project_id, payload
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(event_id) DO NOTHING
                """,
                (
                    event.event_id,
                    event.created_at,
                    event.organization_id,
                    event.project_id,
                    json.dumps(event_payload),
                ),
            )

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
                INSERT INTO trama.operation_events(
                    event_id, created_at, organization_id, project_id, payload
                ) VALUES (%s, %s, %s, %s, %s)
                ON CONFLICT(event_id) DO NOTHING
                """,
                (
                    event.event_id,
                    event.created_at,
                    event.organization_id,
                    event.project_id,
                    json.dumps(event.model_dump(mode="json")),
                ),
            )

    def list_events(self, limit: int = 100) -> list[OperationEvent]:
        bounded_limit = max(1, min(limit, 1000))
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT payload FROM trama.operation_events
                ORDER BY created_at DESC, event_id DESC LIMIT %s
                """,
                (bounded_limit,),
            ).fetchall()
        return [OperationEvent.model_validate(self._payload(row)) for row in reversed(rows)]

    def append_task_log(self, log: TaskLog) -> None:
        message, metadata = sanitize_message(log.message, log.metadata)
        safe_log = log.model_copy(update={"message": message, "metadata": metadata})
        with self._connection() as connection:
            connection.execute(
                """
                INSERT INTO trama.task_logs(
                    log_id, created_at, organization_id, project_id,
                    requirement_id, phase_id, task_id, level, sequence, payload
                ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT(log_id) DO NOTHING
                """,
                (
                    safe_log.log_id,
                    safe_log.created_at,
                    safe_log.organization_id,
                    safe_log.project_id,
                    safe_log.requirement_id,
                    safe_log.phase_id,
                    safe_log.task_id,
                    safe_log.level,
                    safe_log.sequence,
                    json.dumps(safe_log.model_dump(mode="json")),
                ),
            )

    @staticmethod
    def _task_log_filters(
        *,
        organization_id: str | None,
        project_id: str | None,
        task_id: str | None,
        phase_id: str | None,
        requirement_id: str | None,
        level: LogLevel | None,
    ) -> tuple[str, list[str]]:
        clauses = ["TRUE"]
        values: list[str] = []
        for column, value in (
            ("organization_id", organization_id),
            ("project_id", project_id),
            ("task_id", task_id),
            ("phase_id", phase_id),
            ("requirement_id", requirement_id),
            ("level", level),
        ):
            if value is not None:
                clauses.append(f"{column} = %s")
                values.append(value)
        return " AND ".join(clauses), values

    def list_task_logs(
        self,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        phase_id: str | None = None,
        requirement_id: str | None = None,
        level: LogLevel | None = None,
        limit: int = 100,
    ) -> list[TaskLog]:
        bounded_limit = max(1, min(limit, 1000))
        where, values = self._task_log_filters(
            organization_id=organization_id,
            project_id=project_id,
            task_id=task_id,
            phase_id=phase_id,
            requirement_id=requirement_id,
            level=level,
        )
        with self._connection() as connection:
            rows = connection.execute(
                f"SELECT payload FROM trama.task_logs WHERE {where} "
                "ORDER BY created_at ASC, sequence ASC, log_id ASC LIMIT %s",
                [*values, bounded_limit],
            ).fetchall()
        return [TaskLog.model_validate(self._payload(row)) for row in rows]

    def count_task_logs(
        self,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        phase_id: str | None = None,
        requirement_id: str | None = None,
        level: LogLevel | None = None,
    ) -> int:
        where, values = self._task_log_filters(
            organization_id=organization_id,
            project_id=project_id,
            task_id=task_id,
            phase_id=phase_id,
            requirement_id=requirement_id,
            level=level,
        )
        with self._connection() as connection:
            row = connection.execute(
                f"SELECT COUNT(*) AS total FROM trama.task_logs WHERE {where}", values
            ).fetchone()
        return int(row["total"])

    def prune_task_logs(self, organization_id: str, project_id: str, max_rows: int) -> int:
        if max_rows < 0:
            raise ValueError("max_rows debe ser no negativo")
        with self._connection() as connection:
            cursor = connection.execute(
                """
                DELETE FROM trama.task_logs
                WHERE log_id IN (
                    SELECT log_id FROM trama.task_logs
                    WHERE organization_id = %s AND project_id = %s
                    ORDER BY created_at DESC, sequence DESC, log_id DESC
                    OFFSET %s
                )
                """,
                (organization_id, project_id, max_rows),
            )
        return int(cursor.rowcount)

    def count(self, kind: str) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM trama.state_records WHERE kind = %s",
                (kind,),
            ).fetchone()
        return int(row["total"])

    def count_events(self) -> int:
        with self._connection() as connection:
            row = connection.execute(
                "SELECT COUNT(*) AS total FROM trama.operation_events"
            ).fetchone()
        return int(row["total"])


class PostgresTaskInbox:
    """Inbox compartida para redeliveries de JetStream entre varios workers."""

    def __init__(self, database_url: str, *, lease_ttl_seconds: float = 60.0) -> None:
        if lease_ttl_seconds <= 0:
            raise ValueError("lease_ttl_seconds debe ser positivo")
        self.database_url = database_url
        self.lease_ttl_seconds = lease_ttl_seconds
        self._store = PostgresStateStore(database_url)

    @contextmanager
    def _connection(self):
        with self._store._connection() as connection:
            yield connection

    def claim(self, event_id: str) -> InboxDecision:
        now = datetime.now(timezone.utc)
        claimed_until = now + timedelta(seconds=self.lease_ttl_seconds)
        with self._connection() as connection:
            inserted = connection.execute(
                """
                INSERT INTO trama.consumed_events(event_id, claimed_until)
                VALUES (%s, %s)
                ON CONFLICT(event_id) DO NOTHING
                RETURNING event_id
                """,
                (event_id, claimed_until),
            ).fetchone()
            if inserted is not None:
                return "claimed"
            row = connection.execute(
                """
                SELECT claimed_until, completed
                FROM trama.consumed_events
                WHERE event_id = %s
                FOR UPDATE
                """,
                (event_id,),
            ).fetchone()
            if row is None:
                return "in_flight"
            if row["completed"]:
                return "duplicate"
            current_claim = row["claimed_until"]
            if current_claim.tzinfo is None:
                current_claim = current_claim.replace(tzinfo=timezone.utc)
            if current_claim > now:
                return "in_flight"
            connection.execute(
                """
                UPDATE trama.consumed_events
                SET claimed_until = %s
                WHERE event_id = %s AND completed = FALSE
                """,
                (claimed_until, event_id),
            )
            return "claimed"

    def complete(self, event_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE trama.consumed_events
                SET completed = TRUE, claimed_until = CURRENT_TIMESTAMP
                WHERE event_id = %s
                """,
                (event_id,),
            )

    def release(self, event_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE trama.consumed_events
                SET claimed_until = CURRENT_TIMESTAMP
                WHERE event_id = %s AND completed = FALSE
                """,
                (event_id,),
            )


class SqliteTaskInbox:
    """Inbox durable para el consumidor Python local.

    Un claim caduca por tiempo de pared para que un proceso muerto no bloquee
    una redelivery de JetStream después de reiniciar.
    """

    def __init__(self, path: str | Path, *, lease_ttl_seconds: float = 60.0) -> None:
        if lease_ttl_seconds <= 0:
            raise ValueError("lease_ttl_seconds debe ser positivo")
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.lease_ttl_seconds = lease_ttl_seconds
        SqliteStateStore(self.path)
        with self._connection() as connection:
            connection.execute(
                """
                CREATE TABLE IF NOT EXISTS consumed_events (
                    event_id TEXT PRIMARY KEY,
                    claimed_until REAL NOT NULL,
                    completed INTEGER NOT NULL DEFAULT 0
                )
                """
            )

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        try:
            yield connection
            connection.commit()
        finally:
            connection.close()

    def claim(self, event_id: str) -> InboxDecision:
        now = time()
        with self._connection() as connection:
            row = connection.execute(
                "SELECT claimed_until, completed FROM consumed_events WHERE event_id = ?",
                (event_id,),
            ).fetchone()
            if row is None:
                connection.execute(
                    "INSERT INTO consumed_events(event_id, claimed_until) VALUES (?, ?)",
                    (event_id, now + self.lease_ttl_seconds),
                )
                return "claimed"
            if row["completed"]:
                return "duplicate"
            if float(row["claimed_until"]) > now:
                return "in_flight"
            connection.execute(
                "UPDATE consumed_events SET claimed_until = ? WHERE event_id = ?",
                (now + self.lease_ttl_seconds, event_id),
            )
            return "claimed"

    def complete(self, event_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE consumed_events SET completed = 1, claimed_until = 0 WHERE event_id = ?",
                (event_id,),
            )

    def release(self, event_id: str) -> None:
        with self._connection() as connection:
            connection.execute(
                "UPDATE consumed_events SET claimed_until = 0 WHERE event_id = ? AND completed = 0",
                (event_id,),
            )
