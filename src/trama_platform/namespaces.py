"""Reglas de namespace para evitar mezcla accidental entre proyectos."""

from __future__ import annotations

from .contracts import MemoryCandidate, PromotionRequest


def context_namespace(organization_id: str, project_id: str, agent_id: str) -> str:
    return f"context/{organization_id}/{project_id}/{agent_id}"


def knowledge_namespace(organization_id: str, project_id: str) -> str:
    return f"knowledge/{organization_id}/{project_id}"


def artifact_namespace(organization_id: str, project_id: str, task_id: str) -> str:
    return f"artifacts/{organization_id}/{project_id}/{task_id}"


def can_read_candidate(candidate: MemoryCandidate, organization_id: str, project_id: str) -> bool:
    if candidate.organization_id != organization_id:
        return False
    if candidate.visibility == "shared":
        return True
    return candidate.project_id == project_id and candidate.visibility == "project"


def can_promote(request: PromotionRequest, candidate: MemoryCandidate) -> bool:
    return (
        request.organization_id == candidate.organization_id
        and request.project_id == candidate.project_id
        and request.status == "approved"
    )
