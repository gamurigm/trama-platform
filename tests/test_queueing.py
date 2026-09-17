from __future__ import annotations

from threading import Event, Lock

import pytest

from trama_platform.contracts import TaskEnvelope
from trama_platform.queueing import BoundedTaskQueue, QueueCapacityError, TaskDispatcher


def make_task(task_id: str) -> TaskEnvelope:
    return TaskEnvelope(
        task_id=task_id,
        project_id="demo",
        objective="Run tests",
        actor="codex",
        repository="repo-a",
        branch="main",
        worktree="C:/work/demo",
        acceptance_criteria=["tests pass"],
    )


class RecordingCoordination:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def submit_task(self, task: TaskEnvelope) -> str:
        self.seen.append(task.task_id)
        return task.task_id

    def record_result(self, result):
        return None


class BlockingCoordination(RecordingCoordination):
    def __init__(self) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()
        self._lock = Lock()
        self.active = 0
        self.peak = 0

    def submit_task(self, task: TaskEnvelope) -> str:
        with self._lock:
            self.active += 1
            self.peak = max(self.peak, self.active)
        self.started.set()
        self.release.wait(timeout=2)
        with self._lock:
            self.active -= 1
        self.seen.append(task.task_id)
        return task.task_id


def test_bounded_queue_rejects_the_item_over_capacity():
    queue = BoundedTaskQueue(capacity=1)
    queue.put(make_task("task-1"))

    with pytest.raises(QueueCapacityError):
        queue.put(make_task("task-2"))


def test_dispatcher_never_runs_more_than_configured_workers():
    coordination = BlockingCoordination()
    dispatcher = TaskDispatcher(
        coordination,
        queue_capacity=4,
        max_concurrency=2,
        transition=lambda *args: None,
        current_task=lambda organization_id, task_id: make_task(task_id).model_copy(
            update={"organization_id": organization_id}
        ),
    )
    try:
        for index in range(4):
            dispatcher.submit(make_task(f"task-{index}"), persist=lambda: None)

        assert coordination.started.wait(timeout=2)
        coordination.release.set()
        assert dispatcher.wait_for_idle(timeout=2)
        assert coordination.peak <= 2
    finally:
        coordination.release.set()
        dispatcher.close()


def test_dispatcher_resolves_current_task_inside_its_organization():
    coordination = RecordingCoordination()
    seen: list[tuple[str, str]] = []

    def current_task(organization_id: str, task_id: str) -> TaskEnvelope:
        seen.append((organization_id, task_id))
        return make_task(task_id).model_copy(update={"organization_id": organization_id})

    dispatcher = TaskDispatcher(
        coordination,
        queue_capacity=1,
        max_concurrency=1,
        transition=lambda *args: None,
        current_task=current_task,
    )
    try:
        dispatcher.submit(
            make_task("task-1").model_copy(update={"organization_id": "org-b"}),
            persist=lambda: None,
        )
        assert dispatcher.wait_for_idle(timeout=2)
        assert seen == [("org-b", "task-1")]
    finally:
        dispatcher.close()


def test_dispatcher_releases_reservation_when_persistence_fails():
    coordination = RecordingCoordination()
    dispatcher = TaskDispatcher(
        coordination,
        queue_capacity=1,
        max_concurrency=1,
        transition=lambda *args: None,
        current_task=lambda organization_id, task_id: make_task(task_id).model_copy(
            update={"organization_id": organization_id}
        ),
    )
    try:
        with pytest.raises(RuntimeError, match="persist failed"):
            dispatcher.submit(
                make_task("task-1"),
                persist=lambda: (_ for _ in ()).throw(RuntimeError("persist failed")),
            )

        dispatcher.submit(make_task("task-2"), persist=lambda: None)
        assert dispatcher.wait_for_idle(timeout=2)
        assert coordination.seen == ["task-2"]
    finally:
        dispatcher.close()


def test_recovery_releases_reservation_when_queue_is_full():
    class QueueThatFailsRecovery(BoundedTaskQueue):
        failures = 2

        def put(self, task: TaskEnvelope) -> None:
            if self.failures:
                self.failures -= 1
                raise QueueCapacityError("recovery full")
            super().put(task)

    queue = QueueThatFailsRecovery(capacity=1)
    coordination = RecordingCoordination()
    dispatcher = TaskDispatcher(
        coordination,
        queue_capacity=1,
        max_concurrency=1,
        transition=lambda *args: None,
        current_task=lambda organization_id, task_id: make_task(task_id).model_copy(
            update={"organization_id": organization_id}
        ),
        queue=queue,
    )
    try:
        dispatcher.recover([make_task("recovery-1")])
        dispatcher.recover([make_task("recovery-2")])
        dispatcher.submit(make_task("task-1"), persist=lambda: None)
        assert dispatcher.wait_for_idle(timeout=2)
        assert coordination.seen == ["task-1"]
    finally:
        dispatcher.close()


@pytest.mark.parametrize(
    "kwargs",
    [
        {"queue_capacity": 0, "max_concurrency": 1},
        {"queue_capacity": 1, "max_concurrency": 0},
    ],
)
def test_dispatcher_rejects_non_positive_limits(kwargs):
    with pytest.raises(ValueError):
        TaskDispatcher(
            RecordingCoordination(),
            **kwargs,
            transition=lambda *args: None,
            current_task=lambda organization_id, task_id: make_task(task_id).model_copy(
                update={"organization_id": organization_id}
            ),
        )
