import pytest
from pydantic import ValidationError

from trama_platform.contracts import (
    Evidence,
    MemoryCandidate,
    ProjectManifest,
    PromotionRequest,
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


def test_approved_promotion_requires_approval_and_no_conflicts():
    with pytest.raises(ValidationError):
        PromotionRequest(
            promotion_id="promotion-1",
            candidate_id="candidate-1",
            project_id="demo",
            validations=["provenance"],
            status="approved",
        )

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
