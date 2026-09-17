from __future__ import annotations

import os
from uuid import uuid4

import pytest

from trama_platform.contracts import OperationEvent, ProjectManifest, TaskEnvelope
from trama_platform.runtime import TramaRuntime
from trama_platform.state_store import PostgresStateStore


POSTGRES_URL = os.getenv("TRAMA_TEST_POSTGRES_URL")
pytestmark = pytest.mark.skipif(
    not POSTGRES_URL,
    reason="TRAMA_TEST_POSTGRES_URL is required for PostgreSQL integration tests",
)


def _project(organization_id: str, project_id: str) -> ProjectManifest:
    return ProjectManifest(
        organization_id=organization_id,
        project_id=project_id,
        repository="https://example.test/trama",
    )


def _task(organization_id: str, project_id: str, task_id: str) -> TaskEnvelope:
    return TaskEnvelope(
        organization_id=organization_id,
        project_id=project_id,
        task_id=task_id,
        repository="https://example.test/trama",
        objective="Run the distributed smoke test",
        actor="pytest",
        branch="main",
        worktree="C:/work/trama",
        acceptance_criteria=["the task is persisted"],
    )


def test_postgres_registers_project_and_persists_operation_event() -> None:
    organization_id = f"test-org-{uuid4().hex}"
    project_id = f"test-project-{uuid4().hex}"
    store = PostgresStateStore(POSTGRES_URL)
    runtime = TramaRuntime(state_store=store)

    project = runtime.register_project(_project(organization_id, project_id))

    assert next(
        item for item in store.load_projects() if item.project_id == project_id
    ) == project
    event = store.list_events(limit=1)[0]
    assert event.action == "project.register"
    assert event.status == "accepted"
    assert event.organization_id == organization_id
    assert event.project_id == project_id
    runtime.close()


def test_postgres_persists_task_transition_event_fields() -> None:
    organization_id = f"test-org-{uuid4().hex}"
    project_id = f"test-project-{uuid4().hex}"
    task = _task(organization_id, project_id, f"task-{uuid4().hex}")
    event = OperationEvent(
        action="task.dispatch",
        status="accepted",
        organization_id=organization_id,
        project_id=project_id,
        task_id=task.task_id,
    )
    store = PostgresStateStore(POSTGRES_URL)

    store.save_task_transition(task, event)

    assert store.load_tasks()[-1] == task
    assert store.list_events(limit=1)[0].action == "task.dispatch"
