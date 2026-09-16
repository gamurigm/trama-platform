from fastapi.testclient import TestClient

from trama_platform.api import create_app
from trama_platform.runtime import TramaRuntime
from trama_platform.settings import TramaSettings


def _settings() -> TramaSettings:
    return TramaSettings(
        environment="prod",
        database_url="postgresql://trama:secret@db/trama",
        api_token="api-secret",
    )


def _headers(organization_id: str, project_id: str | None = None) -> dict[str, str]:
    headers = {
        "Authorization": "Bearer api-secret",
        "X-Organization-ID": organization_id,
        "X-Actor-ID": "hermes",
        "X-Scopes": "projects:read projects:write tasks:read tasks:write",
    }
    if project_id:
        headers["X-Project-ID"] = project_id
    return headers


def test_production_api_rejects_cross_organization_write():
    client = TestClient(create_app(TramaRuntime(), settings=_settings()))

    response = client.post(
        "/v1/projects",
        headers=_headers("org-a"),
        json={
            "project_id": "demo",
            "organization_id": "org-b",
            "repository": "repo-a",
        },
    )

    assert response.status_code == 403


def test_production_api_binds_project_scope_to_reads_and_writes():
    client = TestClient(create_app(TramaRuntime(), settings=_settings()))
    org_a = _headers("org-a", "demo")

    assert client.post(
        "/v1/projects",
        headers=_headers("org-a"),
        json={"project_id": "demo", "organization_id": "org-a", "repository": "repo-a"},
    ).status_code == 201
    response = client.get("/v1/projects/demo", headers=_headers("org-a", "other"))

    assert response.status_code == 403
    assert client.post(
        "/v1/requirements",
        headers=org_a,
        json={
            "requirement_id": "REQ-1",
            "organization_id": "org-b",
            "project_id": "demo",
            "title": "Cross tenant",
            "description": "must fail",
            "acceptance_criteria": ["forbidden"],
        },
    ).status_code == 403


def test_private_control_plane_requires_gateway_identity():
    settings = _settings()
    settings = settings.__class__(**{
        **settings.__dict__,
        "internal_service_token": "internal-secret",
    })
    client = TestClient(create_app(TramaRuntime(), settings=settings))

    missing = client.get("/v1/status", headers=_headers("org-a"))
    valid_headers = _headers("org-a")
    valid_headers["X-Trama-Internal-Token"] = "internal-secret"
    valid = client.get("/v1/status", headers=valid_headers)

    assert missing.status_code == 401
    assert valid.status_code == 200


def test_production_overview_does_not_disclose_other_organizations():
    runtime = TramaRuntime()
    client = TestClient(create_app(runtime, settings=_settings()))
    assert client.post(
        "/v1/projects",
        headers=_headers("org-a"),
        json={"project_id": "demo-a", "organization_id": "org-a", "repository": "repo-a"},
    ).status_code == 201
    assert client.post(
        "/v1/projects",
        headers=_headers("org-b"),
        json={"project_id": "demo-b", "organization_id": "org-b", "repository": "repo-b"},
    ).status_code == 201
    assert client.post(
        "/v1/requirements",
        headers=_headers("org-b"),
        json={
            "requirement_id": "REQ-B",
            "organization_id": "org-b",
            "project_id": "demo-b",
            "title": "private",
            "description": "private",
            "acceptance_criteria": ["private"],
        },
    ).status_code == 201

    overview = client.get("/v1/overview", headers=_headers("org-a"))

    assert overview.status_code == 200
    assert overview.json()["requirements"] == []
    assert overview.json()["project_id"] is None


def test_production_result_write_must_match_the_task_namespace():
    runtime = TramaRuntime()
    client = TestClient(create_app(runtime, settings=_settings()))
    assert client.post(
        "/v1/projects",
        headers=_headers("org-a"),
        json={"project_id": "demo", "organization_id": "org-a", "repository": "repo-a"},
    ).status_code == 201
    assert client.post(
        "/v1/tasks",
        headers=_headers("org-a"),
        json={
            "task_id": "task-1",
            "organization_id": "org-a",
            "project_id": "demo",
            "objective": "Run tests",
            "actor": "hermes",
            "repository": "repo-a",
            "branch": "main",
            "worktree": "C:/work/demo",
            "acceptance_criteria": ["tests pass"],
        },
    ).status_code == 202

    response = client.post(
        "/v1/results",
        headers=_headers("org-b"),
        json={"task_id": "task-1", "status": "succeeded", "summary": "forbidden"},
    )

    assert response.status_code == 403
