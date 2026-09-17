"""Contratos versionados de TRAMA.

Estos modelos no conocen implementaciones concretas de CCCC, Semantica,
Utopia, MCP ni de un proveedor de modelos. Esa separación permite conectar
proyectos con dependencias propias sin convertirlas en dependencias de TRAMA.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator

Visibility = Literal["private", "project", "shared"]
Sensitivity = Literal["public", "internal", "restricted", "secret"]
TaskLifecycle = Literal[
    "planned",
    "accepted",
    "running",
    "succeeded",
    "partial",
    "failed",
    "blocked",
    "cancelled",
]
RequirementStatus = Literal["proposed", "approved", "in_progress", "completed", "blocked"]
PhaseStatus = Literal["planned", "ready", "in_progress", "completed", "blocked"]
TaskSource = Literal["manual", "requirement"]
LogLevel = Literal["debug", "info", "warning", "error"]
PlanProposalStatus = Literal["proposed", "approved", "rejected", "superseded"]
TimelineKind = Literal["event", "log"]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class TramaContract(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class ProjectPolicies(TramaContract):
    repositories_read_only: bool = True
    allow_external_writes: bool = False
    require_human_approval_for_publish: bool = True
    allow_cross_project_context: bool = False


class ProjectManifest(TramaContract):
    schema_version: Literal["1.0"] = "1.0"
    project_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-z0-9][a-z0-9._-]*$")
    organization_id: str = Field(default="default", min_length=1, max_length=100)
    repository: str = Field(min_length=1, max_length=500)
    default_branch: str = Field(default="main", min_length=1, max_length=200)
    capabilities: list[str] = Field(default_factory=list, max_length=100)
    commands: dict[str, str] = Field(default_factory=dict, max_length=50)
    policies: ProjectPolicies = Field(default_factory=ProjectPolicies)


class Requirement(TramaContract):
    schema_version: Literal["1.0"] = "1.0"
    requirement_id: str = Field(
        min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"
    )
    organization_id: str = Field(default="default", min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    title: str = Field(min_length=1, max_length=300)
    description: str = Field(min_length=1, max_length=10000)
    kind: Literal["feature", "change", "module", "refactor", "bugfix"] = "feature"
    acceptance_criteria: list[str] = Field(min_length=1, max_length=100)
    status: RequirementStatus = "proposed"
    correlation_id: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=utc_now)


class ProjectPhase(TramaContract):
    schema_version: Literal["1.0"] = "1.0"
    phase_id: str = Field(min_length=1, max_length=100, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    requirement_id: str = Field(min_length=1, max_length=100)
    organization_id: str = Field(default="default", min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    name: str = Field(min_length=1, max_length=300)
    sequence: int = Field(ge=1, le=1000)
    depends_on: list[str] = Field(default_factory=list, max_length=100)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=100)
    status: PhaseStatus = "planned"
    correlation_id: str | None = Field(default=None, max_length=200)
    approved_by: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=utc_now)


class ArtifactReference(TramaContract):
    artifact_id: str = Field(min_length=1, max_length=200)
    uri: str = Field(min_length=1, max_length=2000)
    sha256: str = Field(min_length=64, max_length=64, pattern=r"^[a-f0-9]{64}$")
    media_type: str = Field(default="application/octet-stream", max_length=200)
    sensitivity: Sensitivity = "internal"


class TaskEnvelope(TramaContract):
    schema_version: Literal["1.0"] = "1.0"
    task_id: str = Field(min_length=1, max_length=100, pattern=r"^[a-zA-Z0-9][a-zA-Z0-9._:-]*$")
    parent_task_id: str | None = Field(default=None, max_length=100)
    requirement_id: str | None = Field(default=None, max_length=100)
    phase_id: str | None = Field(default=None, max_length=100)
    source: TaskSource = "manual"
    correlation_id: str | None = Field(default=None, max_length=200)
    depends_on: list[str] = Field(default_factory=list, max_length=100)
    approved_by: str | None = Field(default=None, max_length=200)
    organization_id: str = Field(default="default", min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    objective: str = Field(min_length=1, max_length=4000)
    actor: str = Field(min_length=1, max_length=100)
    repository: str = Field(min_length=1, max_length=500)
    branch: str = Field(min_length=1, max_length=200)
    worktree: str = Field(min_length=1, max_length=1000)
    allowed_paths: list[str] = Field(default_factory=list, max_length=500)
    read_only: bool = False
    state: TaskLifecycle = "accepted"
    execution_attempt: int | None = Field(default=None, ge=1, le=1_000_000_000)
    acceptance_criteria: list[str] = Field(min_length=1, max_length=100)
    created_at: datetime = Field(default_factory=utc_now)


class PlanProposal(TramaContract):
    schema_version: Literal["1.0"] = "1.0"
    proposal_id: str = Field(min_length=1, max_length=200)
    requirement_id: str = Field(min_length=1, max_length=100)
    organization_id: str = Field(default="default", min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    model_profile: str = Field(min_length=1, max_length=200)
    input_refs: list[str] = Field(default_factory=list, max_length=100)
    phase_ids: list[str] = Field(default_factory=list, max_length=1000)
    task_ids: list[str] = Field(default_factory=list, max_length=2000)
    summary: str = Field(min_length=1, max_length=10000)
    status: PlanProposalStatus = "proposed"
    version: int = Field(default=1, ge=1, le=1000)
    correlation_id: str = Field(min_length=1, max_length=200)
    approved_by: str | None = Field(default=None, max_length=200)
    created_at: datetime = Field(default_factory=utc_now)


class TaskLog(TramaContract):
    schema_version: Literal["1.0"] = "1.0"
    log_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1, max_length=100)
    created_at: datetime = Field(default_factory=utc_now)
    level: LogLevel = "info"
    message: str = Field(min_length=1, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=50)
    organization_id: str = Field(default="default", min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    requirement_id: str | None = Field(default=None, max_length=100)
    phase_id: str | None = Field(default=None, max_length=100)
    task_id: str | None = Field(default=None, max_length=100)
    actor: str = Field(default="system", min_length=1, max_length=100)
    correlation_id: str = Field(min_length=1, max_length=200)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    sequence: int = Field(default=1, ge=1, le=1_000_000_000)


class TimelineEntry(TramaContract):
    schema_version: Literal["1.0"] = "1.0"
    entry_id: str = Field(min_length=1, max_length=100)
    kind: TimelineKind
    created_at: datetime
    sequence: int = Field(ge=1)
    actor: str = Field(min_length=1, max_length=100)
    action: str | None = Field(default=None, max_length=200)
    status: str | None = Field(default=None, max_length=50)
    level: LogLevel | None = None
    message: str | None = Field(default=None, max_length=4000)
    metadata: dict[str, Any] = Field(default_factory=dict, max_length=50)
    correlation_id: str | None = Field(default=None, max_length=200)
    requirement_id: str | None = Field(default=None, max_length=100)
    phase_id: str | None = Field(default=None, max_length=100)
    task_id: str | None = Field(default=None, max_length=100)


class Verification(TramaContract):
    command: str = Field(min_length=1, max_length=1000)
    status: Literal["passed", "failed", "skipped"]
    summary: str = Field(default="", max_length=2000)


class AgentResult(TramaContract):
    schema_version: Literal["1.0"] = "1.0"
    organization_id: str = Field(default="default", min_length=1, max_length=100)
    task_id: str = Field(min_length=1, max_length=100)
    execution_attempt: int = Field(default=1, ge=1, le=1_000_000_000)
    status: Literal["succeeded", "partial", "failed", "blocked"]
    summary: str = Field(min_length=1, max_length=4000)
    files_changed: list[str] = Field(default_factory=list, max_length=1000)
    commands: list[str] = Field(default_factory=list, max_length=500)
    tests: list[Verification] = Field(default_factory=list, max_length=500)
    artifacts: list[ArtifactReference] = Field(default_factory=list, max_length=500)
    warnings: list[str] = Field(default_factory=list, max_length=200)
    knowledge_candidates: list[str] = Field(default_factory=list, max_length=200)


class Evidence(TramaContract):
    source: str = Field(min_length=1, max_length=500)
    locator: str = Field(min_length=1, max_length=2000)
    commit_sha: str | None = Field(default=None, max_length=64)
    detail: str = Field(default="", max_length=4000)


class MemoryCandidate(TramaContract):
    schema_version: Literal["1.0"] = "1.0"
    candidate_id: str = Field(min_length=1, max_length=200)
    organization_id: str = Field(default="default", min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    agent_id: str | None = Field(default=None, max_length=100)
    task_id: str | None = Field(default=None, max_length=100)
    source: str = Field(default="trama", min_length=1, max_length=500)
    subject: str = Field(min_length=1, max_length=500)
    fact: str = Field(min_length=1, max_length=10000)
    evidence: list[Evidence] = Field(min_length=1, max_length=100)
    confidence: float = Field(ge=0, le=1)
    visibility: Visibility = "project"
    sensitivity: Sensitivity = "internal"
    status: Literal["candidate", "validated", "rejected"] = "candidate"
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def prohibit_secret_sharing(self) -> "MemoryCandidate":
        if self.sensitivity == "secret" and self.visibility != "private":
            raise ValueError("La informacion secreta solo puede tener visibilidad privada")
        return self


class MemorySearchRequest(TramaContract):
    organization_id: str = Field(default="default", min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    agent_id: str | None = Field(default=None, max_length=100)
    query: str = Field(min_length=1, max_length=1000)


class OperationEvent(TramaContract):
    event_id: str = Field(default_factory=lambda: uuid4().hex, min_length=1, max_length=100)
    actor: str = Field(default="system", min_length=1, max_length=100)
    action: str = Field(min_length=1, max_length=200)
    status: Literal["accepted", "succeeded", "failed", "blocked"]
    organization_id: str = Field(default="default", min_length=1, max_length=100)
    project_id: str | None = Field(default=None, max_length=100)
    requirement_id: str | None = Field(default=None, max_length=100)
    phase_id: str | None = Field(default=None, max_length=100)
    task_id: str | None = Field(default=None, max_length=100)
    correlation_id: str | None = Field(default=None, max_length=200)
    duration_ms: int | None = Field(default=None, ge=0, le=86_400_000)
    details: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime = Field(default_factory=utc_now)


class PromotionRequest(TramaContract):
    schema_version: Literal["1.0"] = "1.0"
    promotion_id: str = Field(min_length=1, max_length=200)
    candidate_id: str = Field(min_length=1, max_length=200)
    organization_id: str = Field(default="default", min_length=1, max_length=100)
    project_id: str = Field(min_length=1, max_length=100)
    target: Literal["utopia"] = "utopia"
    visibility: Visibility = "project"
    validations: list[str] = Field(min_length=1, max_length=100)
    conflicts: list[str] = Field(default_factory=list, max_length=100)
    approved_by: str | None = Field(default=None, max_length=200)
    status: Literal["pending", "approved", "rejected"] = "pending"
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def require_clean_approval(self) -> "PromotionRequest":
        if self.status == "approved" and not self.approved_by:
            raise ValueError("Una promocion aprobada requiere approved_by")
        if self.status == "approved" and self.conflicts:
            raise ValueError("No se puede aprobar una promocion con conflictos")
        return self


class ToolInvocation(TramaContract):
    schema_version: Literal["1.0"] = "1.0"
    request_id: str = Field(min_length=1, max_length=200)
    project_id: str = Field(min_length=1, max_length=100)
    agent_id: str = Field(min_length=1, max_length=100)
    tool: str = Field(min_length=1, max_length=300)
    arguments: dict[str, Any] = Field(default_factory=dict)
    approved: bool = False
    sensitivity: Sensitivity = "internal"


class ModelRequest(TramaContract):
    schema_version: Literal["1.0"] = "1.0"
    request_id: str = Field(min_length=1, max_length=200)
    project_id: str = Field(min_length=1, max_length=100)
    agent_id: str = Field(min_length=1, max_length=100)
    model_profile: str = Field(min_length=1, max_length=200)
    purpose: str = Field(min_length=1, max_length=500)
    input_reference: str = Field(min_length=1, max_length=2000)
    max_cost_units: float | None = Field(default=None, ge=0)
    max_seconds: int | None = Field(default=None, ge=1, le=86400)
    sensitivity: Sensitivity = "internal"


class ToolResult(TramaContract):
    request_id: str
    status: Literal["succeeded", "failed"]
    output_reference: str | None = None
    error: str | None = None


class ModelResult(TramaContract):
    request_id: str
    status: Literal["succeeded", "failed"]
    output_reference: str | None = None
    provider: str | None = None
    model: str | None = None
    error: str | None = None
