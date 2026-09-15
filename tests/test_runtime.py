import pytest

from trama_platform.contracts import (
    AgentResult,
    Evidence,
    MemoryCandidate,
    ProjectManifest,
    PromotionRequest,
    TaskEnvelope,
)
from trama_platform.runtime import TramaRuntime


def manifest(project_id: str = "demo") -> ProjectManifest:
    return ProjectManifest(project_id=project_id, repository="https://example.test/repo")


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
