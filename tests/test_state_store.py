from pathlib import Path

from trama_platform.contracts import (
    AgentResult,
    Evidence,
    MemoryCandidate,
    ProjectManifest,
    TaskEnvelope,
)
from trama_platform.runtime import TramaRuntime
from trama_platform.state_store import SqliteStateStore


def _manifest() -> ProjectManifest:
    return ProjectManifest(project_id="demo", organization_id="org-a", repository="repo-a")


def _task() -> TaskEnvelope:
    return TaskEnvelope(
        task_id="task-1",
        organization_id="org-a",
        project_id="demo",
        objective="Run tests",
        actor="codex",
        repository="repo-a",
        branch="main",
        worktree="C:/work/demo",
        acceptance_criteria=["tests pass"],
    )


def test_sqlite_store_round_trips_control_plane_state(tmp_path: Path):
    store = SqliteStateStore(tmp_path / "trama.db")
    runtime = TramaRuntime(state_store=store)
    runtime.register_project(_manifest())
    runtime.submit_task(_task())
    runtime.record_result(AgentResult(task_id="task-1", status="succeeded", summary="ok"))
    runtime.capture_memory(
        MemoryCandidate(
            candidate_id="candidate-1",
            organization_id="org-a",
            project_id="demo",
            subject="tests",
            fact="tests pass",
            evidence=[Evidence(source="ci", locator="run/1")],
            confidence=1,
        )
    )

    restored = TramaRuntime(state_store=SqliteStateStore(tmp_path / "trama.db"))

    assert restored.projects.get("demo").repository == "repo-a"
    assert restored.tasks["task-1"].objective == "Run tests"
    assert restored.coordination.results["task-1"].status == "succeeded"
    assert restored.context_memory.get_candidate("candidate-1").fact == "tests pass"


def test_runtime_records_auditable_events_in_sqlite(tmp_path: Path):
    runtime = TramaRuntime(state_store=SqliteStateStore(tmp_path / "trama.db"))

    runtime.register_project(_manifest())
    runtime.submit_task(_task())

    events = runtime.list_events()

    assert [event.action for event in events] == ["project.register", "task.submit"]
    assert events[-1].project_id == "demo"
    assert events[-1].status == "accepted"
