"""Contratos y runtime mínimo de la plataforma TRAMA."""

from .contracts import (
    AgentResult,
    ArtifactReference,
    MemoryCandidate,
    MemorySearchRequest,
    ModelRequest,
    OperationEvent,
    ProjectManifest,
    PromotionRequest,
    TaskEnvelope,
    ToolInvocation,
)
from .hermes import HermesAdapter
from .lifecycle import GatewaySupervisor
from .mcp_server import TramaApiClient, create_mcp_server
from .runtime import TramaRuntime
from .state_store import SqliteStateStore
from .tui import TramaTuiApp

__all__ = [
    "AgentResult",
    "ArtifactReference",
    "MemoryCandidate",
    "MemorySearchRequest",
    "ModelRequest",
    "OperationEvent",
    "ProjectManifest",
    "PromotionRequest",
    "TaskEnvelope",
    "ToolInvocation",
    "TramaRuntime",
    "TramaApiClient",
    "create_mcp_server",
    "HermesAdapter",
    "GatewaySupervisor",
    "SqliteStateStore",
    "TramaTuiApp",
]
