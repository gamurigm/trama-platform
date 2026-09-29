import asyncio
from pathlib import Path

from trama_platform import worker
from trama_platform.settings import TramaSettings


def test_worker_builds_runtime_with_configured_coordination_and_lease(
    tmp_path: Path,
    monkeypatch,
):
    captured: dict[str, object] = {}

    class FakeRuntime:
        def __init__(self, **kwargs):
            captured["runtime_kwargs"] = kwargs

        def accept_admitted_task(self, task):
            return task.task_id

        def close(self):
            captured["runtime_closed"] = True

    class FakeConsumer:
        def __init__(self, inbox, handler):
            captured["handler"] = handler

        async def run(self, connection, **kwargs):
            captured["consumer_kwargs"] = kwargs

    configured_coordination = object()
    monkeypatch.setattr(worker, "TramaRuntime", FakeRuntime)
    monkeypatch.setattr(worker, "TaskAdmittedConsumer", FakeConsumer)
    monkeypatch.setattr(worker, "build_coordination", lambda settings: configured_coordination)

    settings = TramaSettings(
        coordination_backend="cccc-bridge",
        state_dir=str(tmp_path),
        task_lease_seconds=45,
        queue_capacity=7,
        max_concurrency=2,
        dispatch_timeout_seconds=33,
    )

    asyncio.run(worker.serve_task_worker(settings, connection=object()))

    runtime_kwargs = captured["runtime_kwargs"]
    assert runtime_kwargs["coordination"] is configured_coordination
    assert runtime_kwargs["lease_seconds"] == 45
    assert runtime_kwargs["queue_capacity"] == 7
    assert runtime_kwargs["max_concurrency"] == 2
    assert runtime_kwargs["dispatch_timeout_seconds"] == 33
    assert captured["runtime_closed"] is True
