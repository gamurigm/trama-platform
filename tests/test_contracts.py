import pytest
from pydantic import ValidationError

from trama_platform.contracts import (
    Evidence,
    MemoryCandidate,
    ProjectManifest,
    ProjectPhase,
    PromotionRequest,
    Requirement,
    TaskEnvelope,
)


def evidence() -> list[Evidence]:
    return [Evidence(source="repo", locator="README.md:1", detail="documented fact")]


def test_project_manifest_rejects_unknown_fields():
    with pytest.raises(ValidationError):
        ProjectManifest(project_id="demo", repository="https://example.test/repo", typo=True)


def test_secret_memory_can_only_be_private():
    with pytest.raises(ValidationError):
        MemoryCandidate(
            candidate_id="secret-1",
            project_id="demo",
            subject="credentials",
            fact="private",
            evidence=evidence(),
            confidence=1,
            sensitivity="secret",
            visibility="project",
        )


def test_memory_candidate_carries_agent_and_task_provenance():
    candidate = MemoryCandidate(
        candidate_id="candidate-1",
        organization_id="org-a",
        project_id="demo",
        agent_id="specialist-db",
        task_id="task-1",
        source="semantica",
        subject="audit",
        fact="The trigger writes an audit row",
        evidence=evidence(),
        confidence=0.9,
    )

    assert candidate.agent_id == "specialist-db"
    assert candidate.task_id == "task-1"
    assert candidate.source == "semantica"


def test_approved_promotion_requires_approval_and_no_conflicts():
    with pytest.raises(ValidationError):
        PromotionRequest(
            promotion_id="promotion-1",
            candidate_id="candidate-1",
            project_id="demo",
            validations=["provenance"],
            status="approved",
        )


def test_requirement_phase_and_task_carry_planning_lineage():
    requirement = Requirement(
        requirement_id="REQ-12",
        project_id="demo",
        title="Planificación visual",
        description="Gestionar fases y cola CCCC",
        acceptance_criteria=["La TUI muestra el avance por fase"],
    )
    phase = ProjectPhase(
        phase_id="REQ-12:design",
        requirement_id=requirement.requirement_id,
        project_id="demo",
        name="Diseño",
        sequence=1,
        acceptance_criteria=["Diseño aprobado"],
    )
    task = TaskEnvelope(
        task_id="REQ-12:design:1",
        project_id="demo",
        requirement_id=requirement.requirement_id,
        phase_id=phase.phase_id,
        source="requirement",
        state="planned",
        objective="Definir panel compacto",
        actor="ux-tui",
        repository="repo",
        branch="main",
        worktree="C:/work/demo",
        acceptance_criteria=["Panel legible"],
    )

    assert requirement.status == "proposed"
    assert phase.status == "planned"
    assert task.source == "requirement"
    assert task.state == "planned"

    with pytest.raises(ValidationError):
        PromotionRequest(
            promotion_id="promotion-2",
            candidate_id="candidate-1",
            project_id="demo",
            validations=["provenance"],
            conflicts=["different fact"],
            approved_by="hermes",
            status="approved",
        )
