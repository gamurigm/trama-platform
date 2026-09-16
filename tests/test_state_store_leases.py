import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from pathlib import Path

from trama_platform.contracts import AgentResult, OperationEvent, TaskEnvelope
from trama_platform.leases import TaskLeaseManager
from trama_platform.state_store import SqliteStateStore


def task(task_id: str, *, organization_id: str = "org-a") -> TaskEnvelope:
    return TaskEnvelope(
        task_id=task_id,
        organization_id=organization_id,
        project_id="demo",
        objective="Run tests",
        actor="codex",
        repository="repo-a",
        branch="main",
        worktree="C:/work/demo",
        acceptance_criteria=["tests pass"],
    )


def test_sqlite_claim_is_exclusive_and_expired_lease_can_be_reclaimed(
    tmp_path: Path,
):
    store = SqliteStateStore(tmp_path / "trama.db")
    item = task("task-1")

    first = store.claim_task(item, owner_id="worker-a", lease_seconds=1)
    second = store.claim_task(item, owner_id="worker-b", lease_seconds=1)

    assert first is not None
    assert second is None

    time.sleep(1.1)
    reclaimed = store.claim_task(item, owner_id="worker-b", lease_seconds=1)

    assert reclaimed is not None
    assert reclaimed.owner_id == "worker-b"
    assert reclaimed.attempt == first.attempt + 1


def test_sqlite_claim_is_atomic_for_concurrent_workers(tmp_path: Path):
    database = tmp_path / "trama.db"
    SqliteStateStore(database)
    item = task("task-1")

    def claim(owner_id: str):
        return SqliteStateStore(database).claim_task(
            item,
            owner_id=owner_id,
            lease_seconds=30,
        )

    with ThreadPoolExecutor(max_workers=2) as executor:
        claims = list(executor.map(claim, ("worker-a", "worker-b")))

    assert sum(claim is not None for claim in claims) == 1


def test_sqlite_lease_operations_are_scoped_to_owner_token_and_namespace(
    tmp_path: Path,
):
    store = SqliteStateStore(tmp_path / "trama.db")
    first = store.claim_task(task("task-1"), owner_id="worker-a", lease_seconds=30)
    assert first is not None

    wrong_token = replace(first, lease_token="wrong-token")
    assert store.renew_task_lease(wrong_token, lease_seconds=30) is False
    assert store.complete_task_lease(wrong_token) is False

    assert store.renew_task_lease(first, lease_seconds=30) is True
    assert store.complete_task_lease_for_task("org-a", "task-1") is True
    assert store.complete_task_lease(first) is False

    other_namespace = store.claim_task(
        task("task-1", organization_id="org-b"),
        owner_id="worker-b",
        lease_seconds=30,
    )
    assert other_namespace is not None


def test_sqlite_release_makes_lease_immediately_reclaimable(tmp_path: Path):
    store = SqliteStateStore(tmp_path / "trama.db")
    item = task("task-1")
    first = store.claim_task(item, owner_id="worker-a", lease_seconds=30)
    assert first is not None

    assert store.release_task_lease(first) is True
    reclaimed = store.claim_task(item, owner_id="worker-b", lease_seconds=30)

    assert reclaimed is not None
    assert reclaimed.owner_id == "worker-b"
    assert reclaimed.attempt == first.attempt + 1


def test_sqlite_manager_renews_before_a_second_worker_can_reclaim(tmp_path: Path):
    store = SqliteStateStore(tmp_path / "trama.db")
    manager = TaskLeaseManager(store, owner_id="worker-a", lease_seconds=1)

    try:
        lease = manager.claim(task("task-1"))
        assert lease is not None
        manager.start_renewal(lease)
        time.sleep(1.2)

        assert (
            store.claim_task(task("task-1"), owner_id="worker-b", lease_seconds=1)
            is None
        )
    finally:
        manager.close()


def test_sqlite_legacy_first_attempt_result_closes_claimed_lease(tmp_path: Path):
    store = SqliteStateStore(tmp_path / "trama.db")
    item = task("task-1")
    store.save_task(item)
    lease = store.claim_task(item, owner_id="worker-a", lease_seconds=30)
    assert lease is not None

    result = AgentResult(task_id=item.task_id, status="succeeded", summary="ok")
    terminal = item.model_copy(update={"state": "succeeded"})

    assert store.save_task_result(terminal, result) is True
    persisted = store.load_tasks()[0]
    assert persisted.state == "succeeded"
    assert persisted.execution_attempt == lease.attempt
    assert (
        store.save_task_transition_if_lease_current(
            terminal.model_copy(update={"execution_attempt": lease.attempt}),
            OperationEvent(
                action="task.dispatch",
                status="accepted",
                organization_id=item.organization_id,
                project_id=item.project_id,
                task_id=item.task_id,
            ),
        )
        is False
    )


def test_sqlite_rejects_stale_result_and_dispatch_after_reclaim(tmp_path: Path):
    store = SqliteStateStore(tmp_path / "trama.db")
    item = task("task-1")
    store.save_task(item)
    first = store.claim_task(item, owner_id="worker-a", lease_seconds=1)
    assert first is not None
    first_running = item.model_copy(
        update={"state": "running", "execution_attempt": first.attempt}
    )
    first_event = OperationEvent(
        action="task.dispatch",
        status="accepted",
        organization_id=item.organization_id,
        project_id=item.project_id,
        task_id=item.task_id,
    )
    assert store.save_task_transition_if_lease_current(first_running, first_event)

    time.sleep(1.1)
    second = store.claim_task(item, owner_id="worker-b", lease_seconds=30)
    assert second is not None
    second_running = item.model_copy(
        update={"state": "running", "execution_attempt": second.attempt}
    )
    assert store.save_task_transition_if_lease_current(
        second_running,
        first_event.model_copy(update={"event_id": "dispatch-2"}),
    )

    stale_result = AgentResult(
        task_id=item.task_id,
        execution_attempt=first.attempt,
        status="succeeded",
        summary="stale result",
    )
    stale_terminal = first_running.model_copy(update={"state": "succeeded"})
    assert store.save_task_result(stale_terminal, stale_result) is False
    assert store.load_tasks()[0].execution_attempt == second.attempt
    assert store.load_tasks()[0].state == "running"

    mismatched_result = AgentResult(
        task_id=item.task_id,
        execution_attempt=first.attempt,
        status="succeeded",
        summary="mismatched result",
    )
    mismatched_terminal = second_running.model_copy(update={"state": "succeeded"})
    assert store.save_task_result(mismatched_terminal, mismatched_result) is False

    current_result = stale_result.model_copy(
        update={"execution_attempt": second.attempt, "summary": "current result"}
    )
    current_terminal = second_running.model_copy(update={"state": "succeeded"})
    assert store.save_task_result(current_terminal, current_result) is True
    assert store.save_task_transition_if_lease_current(
        second_running,
        first_event.model_copy(update={"event_id": "dispatch-after-result"}),
    ) is False
