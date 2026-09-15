from pathlib import Path
from threading import Event, Lock

import pytest

from trama_platform.contracts import (
    AgentResult,
    Evidence,
    MemoryCandidate,
    ProjectManifest,
    PromotionRequest,
    TaskEnvelope,
)
from trama_platform.queueing import QueueCapacityError
from trama_platform.runtime import TramaRuntime
from trama_platform.state_store import SqliteStateStore


def manifest(project_id: str = "demo") -> ProjectManifest:
    return ProjectManifest(project_id=project_id, repository="https://example.test/repo")


def scoped_manifest() -> ProjectManifest:
    return ProjectManifest(project_id="demo", organization_id="org-a", repository="repo-a")


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


class RecordingCoordination:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def submit_task(self, item: TaskEnvelope) -> str:
        self.seen.append(item.task_id)
        return item.task_id

    def record_result(self, result: AgentResult) -> None:
        return None


class BlockingCoordination(RecordingCoordination):
    def __init__(self) -> None:
        super().__init__()
        self.started = Event()
        self.release = Event()
        self._lock = Lock()
        self.active = 0

    def submit_task(self, item: TaskEnvelope) -> str:
        with self._lock:
            self.active += 1
        self.started.set()
        self.release.wait(timeout=2)
        with self._lock:
            self.active -= 1
        return super().submit_task(item)


def runtime_with_blocking_coordination(
    *, queue_capacity: int, max_concurrency: int
) -> tuple[TramaRuntime, BlockingCoordination]:
    coordination = BlockingCoordination()
    runtime = TramaRuntime(
        coordination=coordination,
        queue_capacity=queue_capacity,
        max_concurrency=max_concurrency,
    )
    return runtime, coordination


def test_runtime_keeps_projects_and_tasks_in_their_contract_boundary():
    runtime = TramaRuntime()
    runtime.register_project(manifest())
    task = TaskEnvelope(
        task_id="task-1",
        project_id="demo",
        objective="Run tests",
        actor="codex",
        repository="https://example.test/repo",
        branch="main",
        worktree="C:/work/demo",
        acceptance_criteria=["tests pass"],
    )

    assert runtime.submit_task(task) == "task-1"
    runtime.record_result(AgentResult(task_id="task-1", status="succeeded", summary="ok"))
    assert runtime.coordination.results["task-1"].status == "succeeded"


def test_runtime_requires_registered_project():
    runtime = TramaRuntime()
    task = TaskEnvelope(
        task_id="task-1",
        project_id="missing",
        objective="Run tests",
        actor="codex",
        repository="https://example.test/repo",
        branch="main",
        worktree="C:/work/missing",
        acceptance_criteria=["tests pass"],
    )
    with pytest.raises(KeyError):
        runtime.submit_task(task)


def test_runtime_rejects_task_from_another_organization():
    runtime = TramaRuntime()
    runtime.register_project(manifest())
    task = TaskEnvelope(
        task_id="task-cross-org",
        organization_id="other-org",
        project_id="demo",
        objective="Run tests",
        actor="codex",
        repository="https://example.test/repo",
        branch="main",
        worktree="C:/work/demo",
        acceptance_criteria=["tests pass"],
    )

    with pytest.raises(ValueError, match="organizacion"):
        runtime.submit_task(task)


def test_runtime_searches_shared_memory_only_inside_the_organization():
    runtime = TramaRuntime()
    runtime.register_project(
        ProjectManifest(project_id="demo", organization_id="org-a", repository="repo-a")
    )
    runtime.register_project(
        ProjectManifest(project_id="other", organization_id="org-b", repository="repo-b")
    )
    candidate_a = MemoryCandidate(
        candidate_id="shared-a",
        organization_id="org-a",
        project_id="demo",
        subject="tests",
        fact="tests pass in org-a",
        evidence=[Evidence(source="ci", locator="run/a")],
        confidence=1,
        visibility="shared",
    )
    candidate_b = candidate_a.model_copy(
        update={
            "candidate_id": "shared-b",
            "organization_id": "org-b",
            "project_id": "other",
            "fact": "tests pass in org-b",
        }
    )
    runtime.capture_memory(candidate_a)
    runtime.capture_memory(candidate_b)

    results = runtime.search_memory("org-a", "demo", "tests pass")

    assert [candidate.candidate_id for candidate in results] == ["shared-a"]


def test_validated_memory_can_be_promoted_to_canonical_knowledge():
    runtime = TramaRuntime()
    runtime.register_project(manifest())
    candidate = MemoryCandidate(
        candidate_id="candidate-1",
        project_id="demo",
        subject="test",
        fact="the tests pass",
        evidence=[Evidence(source="ci", locator="run/1", detail="pytest")],
        confidence=1,
        status="validated",
    )
    runtime.capture_memory(candidate)
    request = PromotionRequest(
        promotion_id="promotion-1",
        candidate_id="candidate-1",
        project_id="demo",
        validations=["provenance", "review"],
        approved_by="hermes",
        status="approved",
    )

    assert runtime.promote(request) == "promotion-1"


def test_runtime_lists_agents_and_project_memory_candidates():
    runtime = TramaRuntime()
    runtime.register_project(
        ProjectManifest(project_id="demo", organization_id="org-a", repository="repo-a")
    )
    runtime.submit_task(
        TaskEnvelope(
            task_id="task-agent",
            organization_id="org-a",
            project_id="demo",
            objective="Run tests",
            actor="codex",
            repository="repo-a",
            branch="main",
            worktree="C:/work/demo",
            acceptance_criteria=["tests pass"],
        )
    )
    candidate = MemoryCandidate(
        candidate_id="candidate-demo",
        organization_id="org-a",
        project_id="demo",
        subject="tests",
        fact="tests pass",
        evidence=[Evidence(source="ci", locator="run/1")],
        confidence=1,
    )
    runtime.capture_memory(candidate)

    assert runtime.list_agents() == [{"agent_id": "codex", "tasks": 1, "projects": ["demo"]}]
    assert runtime.list_memory_candidates("org-a", "demo") == [candidate]


def test_runtime_can_cancel_and_retry_a_task():
    runtime = TramaRuntime()
    runtime.register_project(manifest())
    task = TaskEnvelope(
        task_id="task-lifecycle",
        project_id="demo",
        objective="Run tests",
        actor="codex",
        repository="https://example.test/repo",
        branch="main",
        worktree="C:/work/demo",
        acceptance_criteria=["tests pass"],
    )
    runtime.submit_task(task)

    assert runtime.cancel_task("task-lifecycle").state == "cancelled"
    assert runtime.retry_task("task-lifecycle").state == "accepted"


def test_runtime_persists_task_before_dispatch(tmp_path: Path):
    coordination = RecordingCoordination()
    store = SqliteStateStore(tmp_path / "trama.db")
    runtime = TramaRuntime(
        coordination=coordination,
        state_store=store,
        queue_capacity=1,
        max_concurrency=1,
    )
    try:
        runtime.register_project(scoped_manifest())
        assert runtime.submit_task(task()) == "task-1"
        assert runtime.wait_for_idle(timeout=2)
        assert coordination.seen == ["task-1"]
        assert [item.task_id for item in store.load_tasks()] == ["task-1"]
    finally:
        runtime.close()


def test_runtime_does_not_mutate_state_when_capacity_is_exhausted():
    runtime, coordination = runtime_with_blocking_coordination(
        queue_capacity=1,
        max_concurrency=1,
    )
    try:
        runtime.register_project(scoped_manifest())
        runtime.submit_task(task("task-1"))
        assert coordination.started.wait(timeout=2)
        runtime.submit_task(task("task-2"))
        with pytest.raises(QueueCapacityError):
            runtime.submit_task(task("task-3"))
        assert "task-3" not in runtime.tasks
    finally:
        coordination.release.set()
        runtime.close()


def test_runtime_records_dispatch_failure_as_terminal_state_and_event():
    class BrokenCoordination(RecordingCoordination):
        def submit_task(self, item: TaskEnvelope) -> str:
            raise RuntimeError("coordinator unavailable")

    runtime = TramaRuntime(coordination=BrokenCoordination())
    try:
        runtime.register_project(scoped_manifest())
        runtime.submit_task(task())
        assert runtime.wait_for_idle(timeout=2)
        assert runtime.tasks["task-1"].state == "failed"
        assert runtime.list_events()[-1].action == "task.dispatch"
    finally:
        runtime.close()


def test_runtime_does_not_enqueue_an_identical_task_twice():
    coordination = RecordingCoordination()
    runtime = TramaRuntime(coordination=coordination)
    try:
        runtime.register_project(scoped_manifest())
        item = task()
        assert runtime.submit_task(item) == "task-1"
        assert runtime.submit_task(item) == "task-1"
        assert runtime.wait_for_idle(timeout=2)
        assert coordination.seen == ["task-1"]
        assert [event.action for event in runtime.list_events()].count("task.submit") == 1
    finally:
        runtime.close()


def test_cancelled_queued_task_is_not_dispatched():
    runtime, coordination = runtime_with_blocking_coordination(
        queue_capacity=1,
        max_concurrency=1,
    )
    try:
        runtime.register_project(scoped_manifest())
        runtime.submit_task(task("task-1"))
        assert coordination.started.wait(timeout=2)
        runtime.submit_task(task("task-2"))
        assert runtime.cancel_task("task-2").state == "cancelled"
        coordination.release.set()
        assert runtime.wait_for_idle(timeout=2)
        assert coordination.seen == ["task-1"]
    finally:
        coordination.release.set()
        runtime.close()


def test_runtime_recovers_running_task_as_accepted(tmp_path: Path):
    store = SqliteStateStore(tmp_path / "trama.db")
    first_coordination = RecordingCoordination()
    first = TramaRuntime(
        coordination=first_coordination,
        state_store=store,
        queue_capacity=1,
        max_concurrency=1,
    )
    first.register_project(scoped_manifest())
    first.submit_task(task())
    assert first.wait_for_idle(timeout=2)
    assert first.tasks["task-1"].state == "running"
    first.close()

    second_coordination = RecordingCoordination()
    second = TramaRuntime(
        coordination=second_coordination,
        state_store=SqliteStateStore(tmp_path / "trama.db"),
        queue_capacity=1,
        max_concurrency=1,
    )
    try:
        assert second.wait_for_idle(timeout=2)
        assert second.tasks["task-1"].state == "running"
        assert second_coordination.seen == ["task-1"]
    finally:
        second.close()
