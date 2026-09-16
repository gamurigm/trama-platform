from __future__ import annotations

import asyncio

import pytest

from trama_platform.contracts import TaskEnvelope
from trama_platform.local_agents import (
    LocalAgentBridge,
    LocalAgentNode,
    LocalAgentPolicy,
    LocalAgentRegistry,
    LocalAgentUnavailable,
)


def test_local_agent_registry_leases_one_colibri_slot_and_keeps_tenants_isolated():
    registry = LocalAgentRegistry()
    registry.register(
        LocalAgentNode(
            node_id="laptop-a",
            organization_id="org-a",
            project_ids=frozenset({"demo"}),
            agent_id="hermes-worker",
            model_profile="colibri-local",
            capacity=1,
        )
    )

    lease = registry.acquire("org-a", "demo", "colibri-local")

    assert lease.node_id == "laptop-a"
    with pytest.raises(LocalAgentUnavailable):
        registry.acquire("org-a", "demo", "colibri-local")
    with pytest.raises(LocalAgentUnavailable):
        registry.acquire("org-b", "demo", "colibri-local")

    registry.release(lease)
    assert registry.acquire("org-a", "demo", "colibri-local").node_id == "laptop-a"


def local_task(actor: str = "hermes") -> TaskEnvelope:
    return TaskEnvelope(
        task_id="task-local",
        organization_id="org-a",
        project_id="demo",
        objective="Run tests",
        actor=actor,
        repository="repo-a",
        branch="main",
        worktree="C:/work/demo",
        acceptance_criteria=["tests pass"],
    )


def test_local_bridge_keeps_interactive_hermes_manual_and_worker_mode_opt_in():
    registry = LocalAgentRegistry()
    registry.register(
        LocalAgentNode(
            node_id="laptop-a",
            organization_id="org-a",
            project_ids=frozenset({"demo"}),
            agent_id="hermes-worker",
            model_profile="colibri-local",
        )
    )
    seen: list[tuple[str, str]] = []
    bridge = LocalAgentBridge(
        registry,
        lambda task, lease: seen.append((task.task_id, lease.lease_id)),
        policy=LocalAgentPolicy(worker_mode_enabled=False),
    )

    with pytest.raises(PermissionError):
        asyncio.run(bridge.execute(local_task(), "colibri-local", mode="interactive"))
    with pytest.raises(LocalAgentUnavailable, match="worker mode"):
        asyncio.run(
            bridge.execute(
                local_task("hermes-worker"), "colibri-local", mode="worker", approved=True
            )
        )

    result = asyncio.run(
        bridge.execute(local_task(), "colibri-local", mode="interactive", approved=True)
    )
    assert result == "task-local"
    assert seen and seen[0][0] == "task-local"


def test_local_bridge_worker_mode_requires_configured_worker_actor():
    registry = LocalAgentRegistry()
    registry.register(
        LocalAgentNode(
            node_id="laptop-a",
            organization_id="org-a",
            project_ids=frozenset({"demo"}),
            agent_id="hermes-worker",
            model_profile="colibri-local",
        )
    )
    bridge = LocalAgentBridge(
        registry,
        lambda task, _: task.task_id,
        policy=LocalAgentPolicy(worker_mode_enabled=True),
    )

    with pytest.raises(PermissionError, match="worker actor"):
        asyncio.run(
            bridge.execute(
                local_task("hermes"), "colibri-local", mode="worker", approved=True
            )
        )
    assert (
        asyncio.run(
            bridge.execute(
                local_task("hermes-worker"), "colibri-local", mode="worker", approved=True
            )
        )
        == "task-local"
    )


def test_local_agent_leases_expire_and_free_capacity():
    now = 100.0
    registry = LocalAgentRegistry(clock=lambda: now, lease_ttl_seconds=10)
    registry.register(
        LocalAgentNode(
            node_id="laptop-a",
            organization_id="org-a",
            project_ids=frozenset({"demo"}),
            agent_id="hermes-worker",
            model_profile="colibri-local",
        )
    )
    registry.acquire("org-a", "demo", "colibri-local")
    with pytest.raises(LocalAgentUnavailable):
        registry.acquire("org-a", "demo", "colibri-local")

    now = 111.0

    assert registry.acquire("org-a", "demo", "colibri-local").node_id == "laptop-a"
