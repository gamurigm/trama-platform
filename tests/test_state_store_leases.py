import time
from dataclasses import replace
from pathlib import Path

from trama_platform.contracts import TaskEnvelope
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
