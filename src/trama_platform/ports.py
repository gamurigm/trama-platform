"""Puertos que desacoplan TRAMA de proveedores y proyectos externos."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .contracts import (
    AgentResult,
    MemoryCandidate,
    ModelRequest,
    ModelResult,
    OperationEvent,
    ProjectManifest,
    PromotionRequest,
    TaskEnvelope,
    ToolInvocation,
    ToolResult,
)


class StateStorePort(Protocol):
    def save_project(self, project: ProjectManifest) -> None: ...

    def load_projects(self) -> Sequence[ProjectManifest]: ...

    def save_task(self, task: TaskEnvelope) -> None: ...

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


class CoordinationPort(Protocol):
    def submit_task(self, task: TaskEnvelope) -> str: ...

    def record_result(self, result: AgentResult) -> None: ...


class ContextMemoryPort(Protocol):
    def put_candidate(self, candidate: MemoryCandidate) -> str: ...

    def get_candidate(self, candidate_id: str) -> MemoryCandidate | None: ...

    def search(
        self, organization_id: str, project_id: str, query: str
    ) -> Sequence[MemoryCandidate]: ...


class CanonicalKnowledgePort(Protocol):
    def publish(self, request: PromotionRequest, candidate: MemoryCandidate) -> str: ...


class ToolGatewayPort(Protocol):
    def invoke(self, invocation: ToolInvocation) -> ToolResult: ...


class ModelGatewayPort(Protocol):
    def complete(self, request: ModelRequest) -> ModelResult: ...
