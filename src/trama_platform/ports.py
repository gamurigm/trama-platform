"""Puertos que desacoplan TRAMA de proveedores y proyectos externos."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .contracts import (
    AgentResult,
    LogLevel,
    MemoryCandidate,
    ModelRequest,
    ModelResult,
    OperationEvent,
    PlanProposal,
    ProjectManifest,
    ProjectPhase,
    PromotionRequest,
    Requirement,
    TaskEnvelope,
    TaskLog,
    TimelineEntry,
    ToolInvocation,
    ToolResult,
)
from .leases import TaskLeaseStore


class StateStorePort(TaskLeaseStore, Protocol):
    def save_project(self, project: ProjectManifest) -> None: ...

    def load_projects(self) -> Sequence[ProjectManifest]: ...

    def save_requirement(self, requirement: Requirement) -> None: ...

    def load_requirements(self) -> Sequence[Requirement]: ...

    def save_plan_proposal(self, proposal: PlanProposal) -> None: ...

    def load_plan_proposals(self) -> Sequence[PlanProposal]: ...

    def save_phase(self, phase: ProjectPhase) -> None: ...

    def load_phases(self) -> Sequence[ProjectPhase]: ...

    def save_task(self, task: TaskEnvelope) -> None: ...

    def save_task_transition(self, task: TaskEnvelope, event: OperationEvent) -> None: ...

    def load_tasks(self) -> Sequence[TaskEnvelope]: ...

    def save_result(self, result: AgentResult) -> None: ...

    def load_results(self) -> Sequence[AgentResult]: ...

    def save_candidate(self, candidate: MemoryCandidate) -> None: ...

    def load_candidates(self) -> Sequence[MemoryCandidate]: ...

    def save_promotion(self, promotion: PromotionRequest) -> None: ...

    def load_promotions(self) -> Sequence[PromotionRequest]: ...

    def append_event(self, event: OperationEvent) -> None: ...

    def list_events(self, limit: int = 100) -> Sequence[OperationEvent]: ...

    def count(self, kind: str) -> int: ...

    def count_events(self) -> int: ...

    def append_task_log(self, log: TaskLog) -> None: ...

    def list_task_logs(
        self,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        phase_id: str | None = None,
        requirement_id: str | None = None,
        level: LogLevel | None = None,
        limit: int = 100,
    ) -> Sequence[TaskLog]: ...

    def count_task_logs(
        self,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        phase_id: str | None = None,
        requirement_id: str | None = None,
        level: LogLevel | None = None,
    ) -> int: ...

    def prune_task_logs(self, organization_id: str, project_id: str, max_rows: int) -> int: ...


class CoordinationPort(Protocol):
    def submit_task(self, task: TaskEnvelope) -> str: ...

    def record_result(self, result: AgentResult) -> None: ...


class TaskQueuePort(Protocol):
    capacity: int

    def put(self, task: TaskEnvelope) -> None: ...

    def get(self, timeout: float | None = None) -> TaskEnvelope | None: ...

    def task_done(self) -> None: ...

    def qsize(self) -> int: ...

    def close(self) -> None: ...


class ContextMemoryPort(Protocol):
    def put_candidate(self, candidate: MemoryCandidate) -> str: ...

    def get_candidate(self, candidate_id: str) -> MemoryCandidate | None: ...

    def search(
        self, organization_id: str, project_id: str, query: str, agent_id: str | None = None
    ) -> Sequence[MemoryCandidate]: ...


class CanonicalKnowledgePort(Protocol):
    def publish(self, request: PromotionRequest, candidate: MemoryCandidate) -> str: ...


class ToolGatewayPort(Protocol):
    def invoke(self, invocation: ToolInvocation) -> ToolResult: ...


class ModelGatewayPort(Protocol):
    def complete(self, request: ModelRequest) -> ModelResult: ...


class TimelinePort(Protocol):
    def task_timeline(self, task_id: str, limit: int = 100) -> Sequence[TimelineEntry]: ...

    def phase_timeline(self, phase_id: str, limit: int = 100) -> Sequence[TimelineEntry]: ...
