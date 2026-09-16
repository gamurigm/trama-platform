from __future__ import annotations

from datetime import datetime, timedelta, timezone
from threading import Event, Lock
from uuid import uuid4

import pytest

from trama_platform.contracts import TaskEnvelope
from trama_platform.leases import TaskLease, TaskLeaseManager


def task(task_id: str = "task-1") -> TaskEnvelope:
    return TaskEnvelope(
        task_id=task_id,
        organization_id="org-a",
        project_id="demo",
        objective="Run tests",
        actor="codex",
        repository="repo-a",
        branch="main",
        worktree="C:/work/demo",
        acceptance_criteria=["tests pass"],
    )


class RecordingLeaseStore:
    def __init__(self, *, claim: bool = True) -> None:
        self.claim_enabled = claim
        self.claimed: list[TaskLease] = []
        self.renewed: list[TaskLease] = []
        self.completed: list[TaskLease] = []
        self.completed_by_task: list[tuple[str, str]] = []
        self.released: list[TaskLease] = []
        self.renewed_event = Event()
        self._lock = Lock()

    def claim_task(
        self, item: TaskEnvelope, *, owner_id: str, lease_seconds: int
    ) -> TaskLease | None:
        if not self.claim_enabled:
            return None
        lease = TaskLease(
            organization_id=item.organization_id,
            task_id=item.task_id,
            owner_id=owner_id,
            lease_token=uuid4().hex,
            attempt=len(self.claimed) + 1,
            expires_at=datetime.now(timezone.utc) + timedelta(seconds=lease_seconds),
        )
        with self._lock:
            self.claimed.append(lease)
        return lease

    def renew_task_lease(self, lease: TaskLease, *, lease_seconds: int) -> bool:
        with self._lock:
            self.renewed.append(lease)
        self.renewed_event.set()
        return True

    def complete_task_lease(self, lease: TaskLease) -> bool:
        with self._lock:
            self.completed.append(lease)
        return True

    def complete_task_lease_for_task(self, organization_id: str, task_id: str) -> bool:
        with self._lock:
            if not any(
                lease.organization_id == organization_id and lease.task_id == task_id
                for lease in self.claimed
            ):
                return False
            self.completed_by_task.append((organization_id, task_id))
        return True

    def release_task_lease(self, lease: TaskLease) -> bool:
        with self._lock:
            self.released.append(lease)
        return True


def test_manager_claims_and_completes_a_task_once():
    store = RecordingLeaseStore()
    manager = TaskLeaseManager(store, owner_id="worker-a", lease_seconds=30)

    try:
        lease = manager.claim(task("task-1"))

        assert lease is not None
        assert lease.owner_id == "worker-a"
        assert manager.complete(task("task-1")) is True
        assert store.completed_by_task == [("org-a", "task-1")]
    finally:
        manager.close()


def test_manager_rejects_non_positive_lease_duration():
    with pytest.raises(ValueError, match="lease_seconds"):
        TaskLeaseManager(RecordingLeaseStore(), owner_id="worker-a", lease_seconds=0)


def test_manager_does_not_track_an_unclaimed_task():
    store = RecordingLeaseStore(claim=False)
    manager = TaskLeaseManager(store, owner_id="worker-a", lease_seconds=30)

    try:
        assert manager.claim(task()) is None
        assert manager.complete(task()) is False
    finally:
        manager.close()


def test_manager_renews_an_active_lease_until_completed():
    store = RecordingLeaseStore()
    manager = TaskLeaseManager(store, owner_id="worker-a", lease_seconds=3)

    try:
        lease = manager.claim(task())
        assert lease is not None
        manager.start_renewal(lease)

        assert store.renewed_event.wait(timeout=2)
        assert manager.complete(task()) is True
        renewed_count = len(store.renewed)
        assert renewed_count >= 1
    finally:
        manager.close()
