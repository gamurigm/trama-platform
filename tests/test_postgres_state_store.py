from __future__ import annotations

import os
import time
from uuid import uuid4

import pytest

from trama_platform.contracts import AgentResult, OperationEvent, ProjectManifest, TaskEnvelope
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

    assert next(item for item in store.load_projects() if item.project_id == project_id) == project
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

    assert next(item for item in store.load_tasks() if item.task_id == task.task_id) == task
    assert store.list_events(limit=1)[0].action == "task.dispatch"


def test_postgres_leases_are_namespace_aware_and_expired_leases_are_reclaimed() -> None:
    task_id = f"task-{uuid4().hex}"
    task_a = _task(f"test-org-a-{uuid4().hex}", "shared-project", task_id)
    task_b = _task(f"test-org-b-{uuid4().hex}", "shared-project", task_id)
    store = PostgresStateStore(POSTGRES_URL)

    first = store.claim_task(task_a, owner_id="worker-a", lease_seconds=1)
    assert first is not None
    assert store.claim_task(task_a, owner_id="worker-b", lease_seconds=1) is None
    other_namespace = store.claim_task(task_b, owner_id="worker-b", lease_seconds=1)
    assert other_namespace is not None

    time.sleep(1.1)
    reclaimed = store.claim_task(task_a, owner_id="worker-b", lease_seconds=30)

    assert reclaimed is not None
    assert reclaimed.owner_id == "worker-b"
    assert reclaimed.attempt == first.attempt + 1


def test_postgres_rejects_stale_result_after_lease_reclaim() -> None:
    task = _task(f"test-org-{uuid4().hex}", "shared-project", f"task-{uuid4().hex}")
    store = PostgresStateStore(POSTGRES_URL)
    store.save_task(task)
    first = store.claim_task(task, owner_id="worker-a", lease_seconds=1)
    assert first is not None
    first_running = task.model_copy(update={"state": "running", "execution_attempt": first.attempt})
    store.save_task_transition_if_lease_current(
        first_running,
        OperationEvent(
            action="task.dispatch",
            status="accepted",
            organization_id=task.organization_id,
            project_id=task.project_id,
            task_id=task.task_id,
        ),
    )

    time.sleep(1.1)
    second = store.claim_task(task, owner_id="worker-b", lease_seconds=30)
    assert second is not None
    second_running = first_running.model_copy(update={"execution_attempt": second.attempt})
    store.save_task_transition_if_lease_current(
        second_running,
        OperationEvent(
            action="task.dispatch",
            status="accepted",
            organization_id=task.organization_id,
            project_id=task.project_id,
            task_id=task.task_id,
        ),
    )

    stale = AgentResult(
        task_id=task.task_id,
        execution_attempt=first.attempt,
        status="succeeded",
        summary="stale result",
        organization_id=task.organization_id,
    )
    assert (
        store.save_task_result(
            first_running.model_copy(update={"state": "succeeded"}), stale
        )
        is False
    )

    current = stale.model_copy(
        update={"execution_attempt": second.attempt, "summary": "current result"}
    )
    assert store.save_task_result(second_running.model_copy(update={"state": "succeeded"}), current)
    assert store.is_task_lease_current(second) is False
