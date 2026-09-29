import asyncio

from trama_platform import worker
from trama_platform.settings import TramaSettings


class EmptySubscription:
    def __init__(self):
        self.messages = self._messages()

    async def _messages(self):
        if False:
            yield None

    async def unsubscribe(self):
        return None


class EmptyJetStream:
    async def subscribe(self, *args, **kwargs):
        return EmptySubscription()


class EmptyConnection:
    def jetstream(self):
        return EmptyJetStream()


def test_worker_passes_configured_coordination_to_runtime(monkeypatch, tmp_path):
    settings = TramaSettings(
        coordination_backend="cccc-bridge",
        cccc_bridge_url="http://bridge.test:8091",
        cccc_bridge_token="bridge-test-token",
        state_dir=str(tmp_path),
    )
    coordination = object()
    captured = {}

    monkeypatch.setattr(
        "trama_platform.cli.build_coordination", lambda configured: coordination
    )

    class Runtime:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def accept_admitted_task(self, task):
            return task.task_id

        def close(self):
            return None

    monkeypatch.setattr(worker, "TramaRuntime", Runtime)

    asyncio.run(
        worker.serve_task_worker(
            settings,
            connection=EmptyConnection(),
        )
    )

    assert captured["coordination"] is coordination
