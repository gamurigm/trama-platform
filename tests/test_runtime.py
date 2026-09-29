import time
from pathlib import Path
from threading import Event, Lock

import httpx
import pytest

from trama_platform.cccc_bridge_client import CcccBridgeCoordination
from trama_platform.contracts import (
    AgentResult,
    Evidence,
    MemoryCandidate,
    PlanProposal,
    ProjectManifest,
    ProjectPhase,
    PromotionRequest,
    Requirement,
    TaskEnvelope,
    TaskLog,
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


def test_unreachable_bridge_marks_dispatch_failed():
    bridge = CcccBridgeCoordination(
        "http://bridge.test",
        "bridge-test-token",
        transport=httpx.MockTransport(
            lambda request: httpx.Response(503, json={"detail": "unavailable"})
        ),
    )
    runtime = TramaRuntime(coordination=bridge, max_concurrency=1)
    runtime.register_project(scoped_manifest())

    runtime.submit_task(task("bridge-unreachable"))

    assert runtime.wait_for_idle(timeout=3)
    assert runtime.tasks["bridge-unreachable"].state == "failed"
    runtime.close()


def test_runtime_close_closes_coordination_once():
    class ClosableCoordination(RecordingCoordination):
        def __init__(self):
            super().__init__()
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    coordination = ClosableCoordination()
    runtime = TramaRuntime(coordination=coordination)

    runtime.close()
    runtime.close()

    assert coordination.close_calls == 1


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


def test_runtime_exposes_a_recorded_task_result():
    runtime = TramaRuntime()
    runtime.register_project(scoped_manifest())
    runtime.submit_task(task("task-result"))
    result = AgentResult(task_id="task-result", status="succeeded", summary="tests pass")

    runtime.record_result(result)

    assert runtime.get_result("task-result") == result.model_copy(
        update={"organization_id": "org-a"}
    )


def test_runtime_isolates_same_project_and_task_ids_by_organization():
    runtime = TramaRuntime()
    runtime.register_project(
        ProjectManifest(project_id="demo", organization_id="org-a", repository="repo-a")
    )
    runtime.register_project(
        ProjectManifest(project_id="demo", organization_id="org-b", repository="repo-b")
    )

    task_a = task("task-1").model_copy(
        update={"organization_id": "org-a", "repository": "repo-a"}
    )
    task_b = task("task-1").model_copy(
        update={"organization_id": "org-b", "repository": "repo-b"}
    )
    runtime.submit_task(task_a)
    runtime.submit_task(task_b)

    assert runtime.get_project("demo", organization_id="org-a").repository == "repo-a"
    assert runtime.get_project("demo", organization_id="org-b").repository == "repo-b"
    assert runtime.get_task("task-1", organization_id="org-a") == task_a
    assert runtime.get_task("task-1", organization_id="org-b") == task_b
    with pytest.raises(ValueError, match="ambigua"):
        runtime.get_task("task-1")


def test_runtime_reviews_memory_candidate_before_promotion():
    runtime = TramaRuntime()
    runtime.register_project(scoped_manifest())
    candidate = MemoryCandidate(
        candidate_id="candidate-review",
        organization_id="org-a",
        project_id="demo",
        subject="tests",
        fact="pytest passes",
        evidence=[Evidence(source="ci", locator="run/1")],
        confidence=1,
    )
    runtime.capture_memory(candidate)

    reviewed = runtime.review_memory_candidate(
        "candidate-review", reviewer="human", status="validated"
    )

    assert reviewed.status == "validated"
    assert runtime.context_memory.get_candidate("candidate-review") == reviewed
    assert runtime.list_events()[-1].action == "memory.validate"


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


def test_runtime_requires_phase_and_task_approval_before_dispatching_derived_tasks():
    coordination = RecordingCoordination()
    runtime = TramaRuntime(coordination=coordination)
    try:
        runtime.register_project(scoped_manifest())
        runtime.register_requirement(
            Requirement(
                requirement_id="REQ-1",
                organization_id="org-a",
                project_id="demo",
                title="Feature",
                description="Feature description",
                acceptance_criteria=["works"],
            )
        )
        runtime.register_phase(
            ProjectPhase(
                phase_id="REQ-1:build",
                requirement_id="REQ-1",
                organization_id="org-a",
                project_id="demo",
                name="Build",
                sequence=1,
                acceptance_criteria=["build passes"],
            )
        )
        planned = task("REQ-1:build:1").model_copy(
            update={
                "requirement_id": "REQ-1",
                "phase_id": "REQ-1:build",
                "source": "requirement",
                "state": "planned",
            }
        )
        runtime.submit_task(planned)
        assert coordination.seen == []
        assert runtime.tasks[planned.task_id].state == "planned"

        runtime.approve_phase("REQ-1:build", approver="human")
        runtime.approve_task(planned.task_id, approver="human")
        assert runtime.wait_for_idle(timeout=2)
        assert coordination.seen == [planned.task_id]
        assert runtime.tasks[planned.task_id].state == "running"
    finally:
        runtime.close()


def test_runtime_overview_groups_phase_progress_queue_and_agents():
    runtime = TramaRuntime()
    try:
        runtime.register_project(scoped_manifest())
        runtime.register_requirement(
            Requirement(
                requirement_id="REQ-1",
                organization_id="org-a",
                project_id="demo",
                title="Feature",
                description="Feature description",
                acceptance_criteria=["works"],
            )
        )
        runtime.register_phase(
            ProjectPhase(
                phase_id="REQ-1:build",
                requirement_id="REQ-1",
                organization_id="org-a",
                project_id="demo",
                name="Build",
                sequence=1,
                acceptance_criteria=["build passes"],
            )
        )
        runtime.approve_phase("REQ-1:build", approver="human")
        runtime.submit_task(
            task("REQ-1:build:1").model_copy(
                update={
                    "requirement_id": "REQ-1",
                    "phase_id": "REQ-1:build",
                    "source": "requirement",
                }
            )
        )
        overview = runtime.overview("demo")
        assert overview["phases"][0]["completed_tasks"] == 0
        assert overview["phases"][0]["total_tasks"] == 1
        assert overview["queue"][0]["task_id"] == "REQ-1:build:1"
        assert overview["agents"][0]["agent_id"] == "codex"
    finally:
        runtime.close()


def test_independent_approved_phases_can_run_in_parallel():
    runtime = TramaRuntime()
    try:
        runtime.register_project(manifest())
        runtime.register_requirement(
            Requirement(
                requirement_id="REQ-1",
                project_id="demo",
                title="Feature",
                description="Feature description",
                acceptance_criteria=["works"],
            )
        )
        for phase_id, name in (("REQ-1:api", "API"), ("REQ-1:tui", "TUI")):
            runtime.register_phase(
                ProjectPhase(
                    phase_id=phase_id,
                    requirement_id="REQ-1",
                    project_id="demo",
                    name=name,
                    sequence=1,
                    acceptance_criteria=["ready"],
                )
            )
            assert runtime.approve_phase(phase_id, approver="human").status == "ready"
        assert {phase.status for phase in runtime.list_phases("demo")} == {"ready"}
    finally:
        runtime.close()


def test_dependent_phase_waits_until_its_phase_dependency_completes():
    runtime = TramaRuntime()
    try:
        runtime.register_project(scoped_manifest())
        runtime.register_requirement(
            Requirement(
                requirement_id="REQ-1",
                organization_id="org-a",
                project_id="demo",
                title="Feature",
                description="Feature description",
                acceptance_criteria=["works"],
            )
        )
        runtime.register_phase(
            ProjectPhase(
                phase_id="REQ-1:api",
                requirement_id="REQ-1",
                organization_id="org-a",
                project_id="demo",
                name="API",
                sequence=1,
                acceptance_criteria=["api ready"],
            )
        )
        runtime.register_phase(
            ProjectPhase(
                phase_id="REQ-1:tui",
                requirement_id="REQ-1",
                organization_id="org-a",
                project_id="demo",
                name="TUI",
                sequence=2,
                depends_on=["REQ-1:api"],
                acceptance_criteria=["tui ready"],
            )
        )
        assert runtime.approve_phase("REQ-1:api", approver="human").status == "ready"
        assert runtime.approve_phase("REQ-1:tui", approver="human").status == "planned"
        phase_task = task("REQ-1:api:1").model_copy(
            update={"requirement_id": "REQ-1", "phase_id": "REQ-1:api"}
        )
        runtime.submit_task(phase_task)
        runtime.record_result(
            AgentResult(task_id=phase_task.task_id, status="succeeded", summary="ok")
        )
        assert runtime.phases["REQ-1:api"].status == "completed"
        assert runtime.phases["REQ-1:tui"].status == "ready"
    finally:
        runtime.close()


def test_runtime_correlates_plan_logs_and_parallel_overview(tmp_path: Path):
    runtime = TramaRuntime(state_store=SqliteStateStore(tmp_path / "trama.db"))
    try:
        runtime.register_project(scoped_manifest())
        runtime.register_requirement(
            Requirement(
                requirement_id="REQ-OBS",
                organization_id="org-a",
                project_id="demo",
                title="Observabilidad",
                description="Ver timeline",
                acceptance_criteria=["timeline visible"],
            )
        )
        for phase_id, name, depends_on in (
            ("REQ-OBS:api", "API", []),
            ("REQ-OBS:tui", "TUI", []),
            ("REQ-OBS:docs", "Docs", ["REQ-OBS:api"]),
        ):
            runtime.register_phase(
                ProjectPhase(
                    phase_id=phase_id,
                    requirement_id="REQ-OBS",
                    organization_id="org-a",
                    project_id="demo",
                    name=name,
                    sequence=len(runtime.phases) + 1,
                    depends_on=depends_on,
                    acceptance_criteria=["ready"],
                )
            )
        api_task = task("REQ-OBS:api:1").model_copy(
            update={
                "requirement_id": "REQ-OBS",
                "phase_id": "REQ-OBS:api",
                "source": "requirement",
                "state": "planned",
                "correlation_id": "corr-obs",
            }
        )
        tui_task = task("REQ-OBS:tui:1").model_copy(
            update={
                "requirement_id": "REQ-OBS",
                "phase_id": "REQ-OBS:tui",
                "source": "requirement",
                "state": "planned",
                "correlation_id": "corr-obs",
            }
        )
        runtime.submit_task(api_task)
        runtime.submit_task(tui_task)
        proposal = PlanProposal(
            proposal_id="plan-obs",
            requirement_id="REQ-OBS",
            organization_id="org-a",
            project_id="demo",
            model_profile="codex-planner",
            phase_ids=["REQ-OBS:api", "REQ-OBS:tui", "REQ-OBS:docs"],
            task_ids=[api_task.task_id, tui_task.task_id],
            summary="Plan paralelo",
            correlation_id="corr-obs",
        )

        runtime.register_plan_proposal(proposal)
        runtime.approve_plan("plan-obs", approver="human")
        runtime.record_task_log(
            TaskLog(
                organization_id="org-a",
                project_id="demo",
                requirement_id="REQ-OBS",
                phase_id="REQ-OBS:api",
                task_id=api_task.task_id,
                actor="cccc",
                correlation_id="corr-obs",
                message="handoff",
                sequence=1,
            )
        )

        overview = runtime.overview("demo")
        timeline = runtime.task_timeline(api_task.task_id)

        assert overview["parallel_groups"] == [
            {"phase_ids": ["REQ-OBS:api", "REQ-OBS:tui"]}
        ]
        assert "REQ-OBS:docs" in overview["blocked_dependencies"]
        assert [entry.kind for entry in timeline][-1] == "log"
        assert all(entry.correlation_id == "corr-obs" for entry in timeline)
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


def test_runtime_can_ingest_a_task_already_admitted_by_the_go_gateway():
    coordination = RecordingCoordination()
    runtime = TramaRuntime(coordination=coordination)
    try:
        runtime.register_project(scoped_manifest())
        item = task("gateway-task")

        assert runtime.accept_admitted_task(item) == "gateway-task"
        assert runtime.accept_admitted_task(item) == "gateway-task"
        assert runtime.wait_for_idle(timeout=2)
        assert coordination.seen == ["gateway-task"]
        assert [event.action for event in runtime.list_events()].count("task.ingest") == 1
    finally:
        runtime.close()


def test_runtime_refreshes_projects_written_by_the_control_api_process(tmp_path: Path):
    database = tmp_path / "trama.db"
    worker_runtime = TramaRuntime(
        coordination=RecordingCoordination(),
        state_store=SqliteStateStore(database),
    )
    try:
        SqliteStateStore(database).save_project(scoped_manifest())

        assert (
            worker_runtime.accept_admitted_task(task("cross-process-task"))
            == "cross-process-task"
        )
        assert worker_runtime.wait_for_idle(timeout=2)
    finally:
        worker_runtime.close()


def test_runtime_reads_tasks_written_by_a_separate_worker_process(tmp_path: Path):
    database = tmp_path / "trama.db"
    api_runtime = TramaRuntime(state_store=SqliteStateStore(database))
    worker_store = SqliteStateStore(database)
    persisted_task = task("cross-process-task").model_copy(update={"state": "running"})
    try:
        worker_store.save_task(persisted_task)

        assert api_runtime.list_tasks() == [persisted_task]
        assert api_runtime.get_task(persisted_task.task_id) == persisted_task
    finally:
        api_runtime.close()


def test_runtime_refreshes_shared_store_before_reads(tmp_path: Path):
    database = tmp_path / "shared.db"
    first = TramaRuntime(state_store=SqliteStateStore(database))
    second = TramaRuntime(state_store=SqliteStateStore(database))
    try:
        first.register_project(scoped_manifest())
        first.submit_task(task("shared-task"))

        assert [item.task_id for item in second.list_tasks()] == ["shared-task"]
    finally:
        first.close()
        second.close()


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


def test_two_runtimes_do_not_dispatch_the_same_recovered_task(tmp_path: Path):
    store = SqliteStateStore(tmp_path / "trama.db")
    first_coordination = RecordingCoordination()
    first = TramaRuntime(
        coordination=first_coordination,
        state_store=store,
        lease_seconds=30,
        queue_capacity=1,
        max_concurrency=1,
    )
    first.register_project(scoped_manifest())
    first.submit_task(task())
    assert first.wait_for_idle(timeout=2)
    assert first.tasks["task-1"].state == "running"

    second_coordination = RecordingCoordination()
    second = TramaRuntime(
        coordination=second_coordination,
        state_store=SqliteStateStore(tmp_path / "trama.db"),
        lease_seconds=30,
        queue_capacity=1,
        max_concurrency=1,
    )
    try:
        assert second.wait_for_idle(timeout=2)
        assert second.tasks["task-1"].state == "running"
        assert second_coordination.seen == []
    finally:
        first.close()
        second.close()


def test_runtime_recovers_task_after_lease_expiration(tmp_path: Path):
    database = tmp_path / "trama.db"
    first_coordination = RecordingCoordination()
    first = TramaRuntime(
        coordination=first_coordination,
        state_store=SqliteStateStore(database),
        lease_seconds=1,
        queue_capacity=1,
        max_concurrency=1,
    )
    first.register_project(scoped_manifest())
    first.submit_task(task())
    assert first.wait_for_idle(timeout=2)
    first.close()

    time.sleep(1.1)
    second_coordination = RecordingCoordination()
    second = TramaRuntime(
        coordination=second_coordination,
        state_store=SqliteStateStore(database),
        lease_seconds=1,
        queue_capacity=1,
        max_concurrency=1,
    )
    try:
        assert second.wait_for_idle(timeout=2)
        assert second_coordination.seen == ["task-1"]
        assert second.tasks["task-1"].state == "running"
    finally:
        second.close()


def test_terminal_task_is_not_redispatched_after_restart(tmp_path: Path):
    database = tmp_path / "trama.db"
    first = TramaRuntime(
        coordination=RecordingCoordination(),
        state_store=SqliteStateStore(database),
        lease_seconds=30,
    )
    first.register_project(scoped_manifest())
    first.submit_task(task())
    assert first.wait_for_idle(timeout=2)
    first.record_result(AgentResult(task_id="task-1", status="succeeded", summary="ok"))
    first.close()

    second_coordination = RecordingCoordination()
    second = TramaRuntime(
        coordination=second_coordination,
        state_store=SqliteStateStore(database),
        lease_seconds=30,
    )
    try:
        assert second.wait_for_idle(timeout=2)
        assert second.tasks["task-1"].state == "succeeded"
        assert second_coordination.seen == []
    finally:
        second.close()
