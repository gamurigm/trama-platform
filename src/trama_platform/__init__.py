"""Contratos y runtime mínimo de la plataforma TRAMA."""

from .contracts import (
    AgentResult,
    ArtifactReference,
    MemoryCandidate,
    MemorySearchRequest,
    ModelRequest,
    ProjectManifest,
    PromotionRequest,
    TaskEnvelope,
    ToolInvocation,
)
from .runtime import TramaRuntime

__all__ = [
    "AgentResult",
    "ArtifactReference",
    "MemoryCandidate",
    "MemorySearchRequest",
    "ModelRequest",
    "ProjectManifest",
    "PromotionRequest",
    "TaskEnvelope",
    "ToolInvocation",
    "TramaRuntime",
]
