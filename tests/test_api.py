from fastapi.testclient import TestClient

from trama_platform.api import create_app
from trama_platform.runtime import TramaRuntime


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
