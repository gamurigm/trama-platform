"""Capacidad local para agentes Python, Hermes y proveedores Colibri."""

from __future__ import annotations

import inspect
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from threading import RLock
from time import monotonic
from typing import Literal
from uuid import uuid4

from .contracts import TaskEnvelope


class LocalAgentUnavailable(RuntimeError):
    """No existe capacidad local segura para el perfil solicitado."""


@dataclass(frozen=True)
class LocalAgentNode:
    node_id: str
    organization_id: str
    project_ids: frozenset[str]
    agent_id: str
    model_profile: str
    capacity: int = 1

    def __post_init__(self) -> None:
        if not self.node_id or not self.organization_id or not self.project_ids:
            raise ValueError("un nodo local requiere identidad, organizacion y proyectos")
        if not self.agent_id or not self.model_profile or self.capacity < 1:
            raise ValueError("un nodo local requiere agente, perfil y capacidad positiva")


@dataclass(frozen=True)
class LocalAgentLease:
    lease_id: str
    node_id: str
    organization_id: str
    project_id: str
    model_profile: str
    expires_at: float = 0.0


@dataclass(frozen=True)
class LocalAgentPolicy:
    """Guardrails for local execution modes.

    Interactive Hermes is approval-gated. Worker mode is intentionally opt-in
    and restricted to a dedicated actor identity so a normal task cannot turn
    a developer laptop into an unattended executor.
    """

    worker_mode_enabled: bool = False
    worker_actor_id: str = "hermes-worker"
    manual_approval_required: bool = True


class LocalAgentRegistry:
    """Registro thread-safe de slots locales; no sustituye la cola durable."""

    def __init__(
        self,
        *,
        clock: Callable[[], float] = monotonic,
        lease_ttl_seconds: float = 60.0,
    ) -> None:
        if lease_ttl_seconds <= 0:
            raise ValueError("lease_ttl_seconds debe ser positivo")
        self._nodes: dict[str, LocalAgentNode] = {}
        self._leases: dict[str, LocalAgentLease] = {}
        self._active_by_node: dict[str, int] = {}
        self._clock = clock
        self._lease_ttl_seconds = lease_ttl_seconds
        self._lock = RLock()

    def register(self, node: LocalAgentNode) -> None:
        with self._lock:
            self._nodes[node.node_id] = node
            self._active_by_node.setdefault(node.node_id, 0)

    def acquire(
        self,
        organization_id: str,
        project_id: str,
        model_profile: str,
    ) -> LocalAgentLease:
        with self._lock:
            self._expire_leases_locked()
            for node in sorted(self._nodes.values(), key=lambda item: item.node_id):
                if (
                    node.organization_id == organization_id
                    and project_id in node.project_ids
                    and node.model_profile == model_profile
                    and self._active_by_node[node.node_id] < node.capacity
                ):
                    lease = LocalAgentLease(
                        lease_id=uuid4().hex,
                        node_id=node.node_id,
                        organization_id=organization_id,
                        project_id=project_id,
                        model_profile=model_profile,
                        expires_at=self._clock() + self._lease_ttl_seconds,
                    )
                    self._leases[lease.lease_id] = lease
                    self._active_by_node[node.node_id] += 1
                    return lease
        raise LocalAgentUnavailable("no hay capacidad local para el perfil solicitado")

    def renew(self, lease: LocalAgentLease) -> LocalAgentLease:
        with self._lock:
            self._expire_leases_locked()
            current = self._leases.get(lease.lease_id)
            if current is None:
                raise LocalAgentUnavailable("el lease local ya no esta vigente")
            renewed = LocalAgentLease(
                lease_id=current.lease_id,
                node_id=current.node_id,
                organization_id=current.organization_id,
                project_id=current.project_id,
                model_profile=current.model_profile,
                expires_at=self._clock() + self._lease_ttl_seconds,
            )
            self._leases[lease.lease_id] = renewed
            return renewed

    def release(self, lease: LocalAgentLease) -> None:
        with self._lock:
            current = self._leases.pop(lease.lease_id, None)
            if current is None:
                return
            self._active_by_node[current.node_id] -= 1

    def _expire_leases_locked(self) -> None:
        now = self._clock()
        expired = [
            lease_id
            for lease_id, lease in self._leases.items()
            if lease.expires_at <= now
        ]
        for lease_id in expired:
            lease = self._leases.pop(lease_id)
            self._active_by_node[lease.node_id] -= 1


LocalAgentRunner = Callable[
    [TaskEnvelope, LocalAgentLease], object | Awaitable[object]
]


class LocalAgentBridge:
    """Presents local Hermes/Colibri capacity as a lease-scoped execution port."""

    def __init__(
        self,
        registry: LocalAgentRegistry,
        runner: LocalAgentRunner,
        *,
        policy: LocalAgentPolicy | None = None,
    ) -> None:
        self.registry = registry
        self.runner = runner
        self.policy = policy or LocalAgentPolicy()

    async def execute(
        self,
        task: TaskEnvelope,
        model_profile: str,
        *,
        mode: Literal["interactive", "worker"] = "interactive",
        approved: bool = False,
    ) -> object:
        if mode == "worker":
            if not self.policy.worker_mode_enabled:
                raise LocalAgentUnavailable("local worker mode is disabled")
            if task.actor != self.policy.worker_actor_id:
                raise PermissionError("worker mode requires the dedicated worker actor")
        elif self.policy.manual_approval_required and not approved:
            raise PermissionError("interactive local execution requires manual approval")

        lease = self.registry.acquire(
            task.organization_id,
            task.project_id,
            model_profile,
        )
        try:
            result = self.runner(task, lease)
            if inspect.isawaitable(result):
                result = await result
            return task.task_id if result is None else result
        finally:
            self.registry.release(lease)
