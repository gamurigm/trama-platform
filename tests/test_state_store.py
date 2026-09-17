import json
import sqlite3
from pathlib import Path

from trama_platform.contracts import (
    AgentResult,
    Evidence,
    MemoryCandidate,
    OperationEvent,
    PlanProposal,
    ProjectManifest,
    TaskEnvelope,
    TaskLog,
    utc_now,
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


def test_sqlite_store_keeps_same_task_id_for_separate_organizations(tmp_path: Path):
    store = SqliteStateStore(tmp_path / "trama.db")
    store.save_task(_task())
    store.save_task(
        _task().model_copy(
            update={"organization_id": "org-b", "repository": "repo-b"}
        )
    )

    restored = SqliteStateStore(tmp_path / "trama.db")

    assert {
        (item.organization_id, item.task_id, item.repository)
        for item in restored.load_tasks()
    } == {
        ("org-a", "task-1", "repo-a"),
        ("org-b", "task-1", "repo-b"),
    }


def test_sqlite_store_keeps_same_result_id_for_separate_organizations(tmp_path: Path):
    store = SqliteStateStore(tmp_path / "trama.db")
    store.save_result(
        AgentResult(
            task_id="task-1",
            organization_id="org-a",
            status="succeeded",
            summary="a",
        )
    )
    store.save_result(
        AgentResult(
            task_id="task-1",
            organization_id="org-b",
            status="succeeded",
            summary="b",
        )
    )

    assert {
        (item.organization_id, item.summary) for item in store.load_results()
    } == {("org-a", "a"), ("org-b", "b")}


def test_sqlite_store_migrates_legacy_records_to_namespace_keys(tmp_path: Path):
    database = tmp_path / "legacy.db"
    legacy_task = _task()
    connection = sqlite3.connect(database)
    connection.execute(
        """
        CREATE TABLE state_records (
            kind TEXT NOT NULL,
            record_id TEXT NOT NULL,
            payload TEXT NOT NULL,
            PRIMARY KEY (kind, record_id)
        )
        """
    )
    connection.execute(
        "INSERT INTO state_records(kind, record_id, payload) VALUES (?, ?, ?)",
        ("task", "task-1", json.dumps(legacy_task.model_dump(mode="json"))),
    )
    connection.commit()
    connection.close()

    store = SqliteStateStore(database)

    loaded = store.load_tasks()
    assert len(loaded) == 1
    assert loaded[0].model_dump(mode="json") == legacy_task.model_dump(mode="json")
    with sqlite3.connect(database) as migrated:
        columns = {row[1] for row in migrated.execute("PRAGMA table_info(state_records)")}
    assert "organization_id" in columns


def test_runtime_records_auditable_events_in_sqlite(tmp_path: Path):
    runtime = TramaRuntime(state_store=SqliteStateStore(tmp_path / "trama.db"))

    runtime.register_project(_manifest())
    runtime.submit_task(_task())
    assert runtime.wait_for_idle(timeout=1.0)

    events = runtime.list_events()

    assert [event.action for event in events] == [
        "project.register",
        "task.submit",
        "task.dispatch",
    ]
    assert events[-1].project_id == "demo"
    assert events[-1].status == "accepted"


def test_runtime_restores_auditable_events_after_restart(tmp_path: Path):
    database = tmp_path / "trama.db"
    first_runtime = TramaRuntime(state_store=SqliteStateStore(database))
    first_runtime.register_project(_manifest())
    first_runtime.close()

    restarted_runtime = TramaRuntime(state_store=SqliteStateStore(database))

    assert [event.action for event in restarted_runtime.list_events()] == [
        "project.register"
    ]
    restarted_runtime.close()


def test_sqlite_store_saves_task_transition_with_its_event(tmp_path: Path):
    store = SqliteStateStore(tmp_path / "trama.db")
    task = _task().model_copy(update={"state": "running"})
    event = OperationEvent(
        action="task.dispatch",
        status="accepted",
        organization_id="org-a",
        project_id="demo",
        details={"task_id": task.task_id},
    )

    store.save_task_transition(task, event)

    assert store.load_tasks() == [task]
    assert store.list_events() == [event]


def _plan() -> PlanProposal:
    return PlanProposal(
        proposal_id="plan-1",
        requirement_id="REQ-1",
        organization_id="org-a",
        project_id="demo",
        model_profile="codex-planner",
        summary="Plan de prueba",
        correlation_id="corr-1",
    )


def _log(
    log_id: str,
    *,
    organization_id: str = "org-a",
    project_id: str = "demo",
    sequence: int = 1,
) -> TaskLog:
    return TaskLog(
        log_id=log_id,
        organization_id=organization_id,
        project_id=project_id,
        task_id="task-1",
        actor="cccc",
        correlation_id="corr-1",
        sequence=sequence,
        message=f"log {sequence}",
    )


def test_sqlite_store_round_trips_plan_proposals_and_task_logs(tmp_path: Path):
    database = tmp_path / "trama.db"
    store = SqliteStateStore(database)
    proposal = _plan()
    store.save_plan_proposal(proposal)
    store.append_task_log(_log("log-1"))

    restored = SqliteStateStore(database)

    assert restored.load_plan_proposals() == [proposal]
    assert restored.list_task_logs(project_id="demo")[0].log_id == "log-1"


def test_sqlite_store_filters_logs_by_tenant_and_orders_sequence(tmp_path: Path):
    store = SqliteStateStore(tmp_path / "trama.db")
    store.append_task_log(_log("log-1", sequence=1))
    store.append_task_log(_log("log-2", sequence=2))
    store.append_task_log(_log("log-3", project_id="other", sequence=3))
    store.append_task_log(_log("log-4", organization_id="org-b", sequence=4))

    logs = store.list_task_logs(organization_id="org-a", project_id="demo")

    assert [item.log_id for item in logs] == ["log-1", "log-2"]


def test_sqlite_store_prunes_oldest_logs_per_project(tmp_path: Path):
    store = SqliteStateStore(tmp_path / "trama.db")
    for index in range(1, 4):
        store.append_task_log(
            _log(f"log-{index}", sequence=index).model_copy(
                update={"created_at": utc_now()}
            )
        )

    deleted = store.prune_task_logs("org-a", "demo", max_rows=2)

    assert deleted == 1
    assert [item.sequence for item in store.list_task_logs(project_id="demo")] == [2, 3]
