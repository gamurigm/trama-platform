"""Contratos y runtime mínimo de la plataforma TRAMA."""

from .colibri import ColibriModelGateway
from .contracts import (
    AgentResult,
    ArtifactReference,
    MemoryCandidate,
    MemorySearchRequest,
    ModelRequest,
    OperationEvent,
    ProjectManifest,
    ProjectPhase,
    PromotionRequest,
    Requirement,
    TaskEnvelope,
    ToolInvocation,
)
from .hermes import HermesAdapter
from .lifecycle import GatewaySupervisor
from .local_agents import (
    LocalAgentBridge,
    LocalAgentLease,
    LocalAgentNode,
    LocalAgentPolicy,
    LocalAgentRegistry,
)
from .mcp_server import TramaApiClient, create_mcp_server
from .nats_consumer import TaskAdmittedConsumer
from .runtime import TramaRuntime
from .state_store import SqliteStateStore, SqliteTaskInbox
from .tui import TramaTuiApp

__all__ = [
    "AgentResult",
    "ArtifactReference",
    "MemoryCandidate",
    "MemorySearchRequest",
    "ModelRequest",
    "OperationEvent",
    "ProjectManifest",
    "ProjectPhase",
    "Requirement",
    "PromotionRequest",
    "TaskEnvelope",
    "ToolInvocation",
    "TramaRuntime",
    "TramaApiClient",
    "create_mcp_server",
    "HermesAdapter",
    "ColibriModelGateway",
    "LocalAgentBridge",
    "LocalAgentLease",
    "LocalAgentNode",
    "LocalAgentPolicy",
    "LocalAgentRegistry",
    "TaskAdmittedConsumer",
    "GatewaySupervisor",
    "SqliteStateStore",
    "SqliteTaskInbox",
    "TramaTuiApp",
]
