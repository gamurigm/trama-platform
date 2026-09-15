"""Puertos que desacoplan TRAMA de proveedores y proyectos externos."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Protocol

from .contracts import (
    AgentResult,
    MemoryCandidate,
    ModelRequest,
    ModelResult,
    PromotionRequest,
    TaskEnvelope,
    ToolInvocation,
    ToolResult,
)


class CoordinationPort(Protocol):
    def submit_task(self, task: TaskEnvelope) -> str: ...

    def record_result(self, result: AgentResult) -> None: ...


class ContextMemoryPort(Protocol):
    def put_candidate(self, candidate: MemoryCandidate) -> str: ...

    def get_candidate(self, candidate_id: str) -> MemoryCandidate | None: ...

    def search(self, project_id: str, query: str) -> Sequence[MemoryCandidate]: ...


class CanonicalKnowledgePort(Protocol):
    def publish(self, request: PromotionRequest, candidate: MemoryCandidate) -> str: ...


class ToolGatewayPort(Protocol):
    def invoke(self, invocation: ToolInvocation) -> ToolResult: ...


class ModelGatewayPort(Protocol):
    def complete(self, request: ModelRequest) -> ModelResult: ...
