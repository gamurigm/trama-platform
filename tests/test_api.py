from threading import Event

from fastapi.testclient import TestClient

from trama_platform.api import create_app
from trama_platform.queueing import QueueCapacityError
from trama_platform.runtime import TramaRuntime
from trama_platform.state_store import SqliteStateStore


def test_api_registers_project_and_accepts_task():
    client = TestClient(create_app(TramaRuntime()))
    project = {
        "project_id": "demo",
        "repository": "https://example.test/repo",
    }
    assert client.post("/v1/projects", json=project).status_code == 201

    task = {
        "task_id": "task-1",
        "project_id": "demo",
        "objective": "Run tests",
        "actor": "codex",
        "repository": "https://example.test/repo",
        "branch": "main",
        "worktree": "C:/work/demo",
        "acceptance_criteria": ["tests pass"],
    }
    response = client.post("/v1/tasks", json=task)
    assert response.status_code == 202
    assert response.json() == {"task_id": "task-1", "status": "accepted"}


def test_api_rejects_task_for_unknown_project():
    client = TestClient(create_app(TramaRuntime()))
    task = {
        "task_id": "task-1",
        "project_id": "missing",
        "objective": "Run tests",
        "actor": "codex",
        "repository": "https://example.test/repo",
        "branch": "main",
        "worktree": "C:/work/missing",
        "acceptance_criteria": ["tests pass"],
    }
    assert client.post("/v1/tasks", json=task).status_code == 404


def test_api_searches_memory_inside_an_organization_and_project():
    runtime = TramaRuntime()
    client = TestClient(create_app(runtime))
    project = {
        "project_id": "demo",
        "organization_id": "org-a",
        "repository": "https://example.test/repo",
    }
    assert client.post("/v1/projects", json=project).status_code == 201
    candidate = {
        "candidate_id": "candidate-a",
        "organization_id": "org-a",
        "project_id": "demo",
        "subject": "tests",
        "fact": "tests pass",
        "evidence": [{"source": "ci", "locator": "run/1"}],
        "confidence": 1,
    }
    assert client.post("/v1/memory/candidates", json=candidate).status_code == 201

    response = client.post(
        "/v1/memory/search",
        json={"organization_id": "org-a", "project_id": "demo", "query": "tests"},
    )

    assert response.status_code == 200
    assert [item["candidate_id"] for item in response.json()] == ["candidate-a"]


def test_api_exposes_control_plane_status_projects_tasks_and_events(tmp_path):
    runtime = TramaRuntime(state_store=SqliteStateStore(tmp_path / "trama.db"))
    client = TestClient(create_app(runtime))
    project = {
        "project_id": "demo",
        "repository": "https://example.test/repo",
    }
    assert client.post("/v1/projects", json=project).status_code == 201
    task = {
        "task_id": "task-1",
        "project_id": "demo",
        "objective": "Run tests",
        "actor": "codex",
        "repository": "https://example.test/repo",
        "branch": "main",
        "worktree": "C:/work/demo",
        "acceptance_criteria": ["tests pass"],
    }
    assert client.post("/v1/tasks", json=task).status_code == 202
    assert runtime.wait_for_idle(timeout=2)

    status = client.get("/v1/status")
    assert status.status_code == 200
    assert status.json()["projects"] == 1
    assert status.json()["tasks"] == 1
    assert [item["project_id"] for item in client.get("/v1/projects").json()] == ["demo"]
    assert [item["task_id"] for item in client.get("/v1/tasks").json()] == ["task-1"]
    assert [item["action"] for item in client.get("/v1/events").json()] == [
        "project.register",
        "task.submit",
        "task.dispatch",
    ]


def test_api_status_counts_results_with_external_coordination(tmp_path):
    class FakeCoordination:
        def submit_task(self, task):
            return task.task_id

        def record_result(self, result):
            return None

    runtime = TramaRuntime(
        coordination=FakeCoordination(),
        state_store=SqliteStateStore(tmp_path / "trama.db"),
    )
    client = TestClient(create_app(runtime))
    assert client.post(
        "/v1/projects",
        json={"project_id": "demo", "repository": "repo-a"},
    ).status_code == 201
    assert client.post(
        "/v1/tasks",
        json={
            "task_id": "task-1",
            "project_id": "demo",
            "objective": "Run tests",
            "actor": "hermes",
            "repository": "repo-a",
            "branch": "main",
            "worktree": "C:/work/demo",
            "acceptance_criteria": ["tests pass"],
        },
    ).status_code == 202
    assert client.post(
        "/v1/results",
        json={"task_id": "task-1", "status": "succeeded", "summary": "ok"},
    ).status_code == 202

    assert client.get("/v1/status").json()["results"] == 1


def test_api_lists_agents_and_memory_candidates_in_the_project_namespace():
    runtime = TramaRuntime()
    client = TestClient(create_app(runtime))
    assert client.post(
        "/v1/projects",
        json={
            "project_id": "demo",
            "organization_id": "org-a",
            "repository": "repo-a",
        },
    ).status_code == 201
    assert client.post(
        "/v1/tasks",
        json={
            "task_id": "task-1",
            "organization_id": "org-a",
            "project_id": "demo",
            "objective": "Run tests",
            "actor": "codex",
            "repository": "repo-a",
            "branch": "main",
            "worktree": "C:/work/demo",
            "acceptance_criteria": ["tests pass"],
        },
    ).status_code == 202
    assert client.post(
        "/v1/memory/candidates",
        json={
            "candidate_id": "candidate-1",
            "organization_id": "org-a",
            "project_id": "demo",
            "subject": "tests",
            "fact": "tests pass",
            "evidence": [{"source": "ci", "locator": "run/1"}],
            "confidence": 1,
        },
    ).status_code == 201

    assert client.get("/v1/agents").json() == [
        {"agent_id": "codex", "tasks": 1, "projects": ["demo"]}
    ]
    candidates = client.get(
        "/v1/memory/candidates",
        params={"organization_id": "org-a", "project_id": "demo"},
    )
    assert [item["candidate_id"] for item in candidates.json()] == ["candidate-1"]


def test_api_inspects_registered_project_and_task():
    client = TestClient(create_app(TramaRuntime()))
    project = {
        "project_id": "demo",
        "repository": "https://example.test/repo",
    }
    assert client.post("/v1/projects", json=project).status_code == 201
    task = {
        "task_id": "task-1",
        "project_id": "demo",
        "objective": "Run tests",
        "actor": "codex",
        "repository": "https://example.test/repo",
        "branch": "main",
        "worktree": "C:/work/demo",
        "acceptance_criteria": ["tests pass"],
    }
    assert client.post("/v1/tasks", json=task).status_code == 202

    assert client.get("/v1/projects/demo").json()["project_id"] == "demo"
    assert client.get("/v1/tasks/task-1").json()["objective"] == "Run tests"


def test_api_can_cancel_and_retry_a_task():
    client = TestClient(create_app(TramaRuntime()))
    assert client.post(
        "/v1/projects",
        json={"project_id": "demo", "repository": "repo-a"},
    ).status_code == 201
    assert client.post(
        "/v1/tasks",
        json={
            "task_id": "task-1",
            "project_id": "demo",
            "objective": "Run tests",
            "actor": "codex",
            "repository": "repo-a",
            "branch": "main",
            "worktree": "C:/work/demo",
            "acceptance_criteria": ["tests pass"],
        },
    ).status_code == 202

    assert client.post("/v1/tasks/task-1/cancel").json()["state"] == "cancelled"
    assert client.post("/v1/tasks/task-1/retry").json()["state"] == "accepted"


def test_api_returns_queue_full_and_dispatcher_metrics():
    class BlockingCoordination:
        def __init__(self):
            self.started = Event()
            self.release = Event()

        def submit_task(self, task):
            self.started.set()
            self.release.wait(timeout=2)
            return task.task_id

        def record_result(self, result):
            return None

    coordination = BlockingCoordination()
    runtime = TramaRuntime(
        coordination=coordination,
        queue_capacity=1,
        max_concurrency=1,
    )
    client = TestClient(create_app(runtime))
    project = {"project_id": "demo", "repository": "repo-a"}

    def task_payload(task_id):
        return {
            "task_id": task_id,
            "project_id": "demo",
            "objective": "Run tests",
            "actor": "codex",
            "repository": "repo-a",
            "branch": "main",
            "worktree": "C:/work/demo",
            "acceptance_criteria": ["tests pass"],
        }

    try:
        assert client.post("/v1/projects", json=project).status_code == 201
        assert client.post("/v1/tasks", json=task_payload("task-1")).status_code == 202
        assert coordination.started.wait(timeout=2)
        assert client.post("/v1/tasks", json=task_payload("task-2")).status_code == 202

        response = client.post("/v1/tasks", json=task_payload("task-3"))

        assert response.status_code == 429
        assert response.headers["retry-after"] == "1"
        assert response.json()["detail"] == {
            "code": "queue_full",
            "message": "La cola de tareas está llena",
        }
        assert "task-3" not in runtime.tasks
        status = client.get("/v1/status").json()
        assert status["queue_depth"] == 1
        assert status["queue_capacity"] == 1
        assert status["active_dispatches"] == 1
        assert status["max_concurrency"] == 1
        assert status["dispatcher_status"] == "running"
    finally:
        coordination.release.set()
        runtime.close()


def test_api_maps_queue_full_on_task_retry():
    class FullRuntime:
        def retry_task(self, task_id):
            raise QueueCapacityError("full")

    client = TestClient(create_app(FullRuntime()))

    response = client.post("/v1/tasks/task-1/retry")

    assert response.status_code == 429
    assert response.headers["retry-after"] == "1"


def test_api_closes_runtime_once_during_lifespan():
    class ClosableRuntime:
        def __init__(self):
            self.close_calls = 0

        def close(self):
            self.close_calls += 1

    runtime = ClosableRuntime()
    with TestClient(create_app(runtime)):
        pass

    assert runtime.close_calls == 1
