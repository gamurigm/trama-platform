from __future__ import annotations

import asyncio
import json

import pytest

from trama_platform.contracts import TaskEnvelope
from trama_platform.nats_consumer import InMemoryTaskInbox, TaskAdmittedConsumer
from trama_platform.state_store import SqliteTaskInbox


def task_payload(task_id: str = "task-1") -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "task_id": task_id,
        "organization_id": "org-a",
        "project_id": "demo",
        "objective": "Run tests",
        "actor": "hermes",
        "repository": "repo-a",
        "branch": "main",
        "worktree": "C:/work/demo",
        "acceptance_criteria": ["tests pass"],
    }


class FakeMessage:
    def __init__(self, payload: object, event_id: str = "event-1") -> None:
        self.data = json.dumps(payload).encode("utf-8")
        self.headers = {"Nats-Msg-Id": event_id}
        self.ack_count = 0

    async def ack(self) -> None:
        self.ack_count += 1


class FakeSubscription:
    def __init__(self, messages: list[FakeMessage]) -> None:
        self._messages = messages
        self.unsubscribed = False

    async def _iterate(self):
        for message in self._messages:
            yield message

    @property
    def messages(self):
        return self._iterate()

    async def unsubscribe(self) -> None:
        self.unsubscribed = True


class FakeJetStream:
    def __init__(self, subscription: FakeSubscription) -> None:
        self.subscription = subscription
        self.arguments: dict[str, object] = {}

    async def subscribe(self, subject: str, **kwargs):
        self.arguments = {"subject": subject, **kwargs}
        return self.subscription


class FakeConnection:
    def __init__(self, jetstream: FakeJetStream) -> None:
        self._jetstream = jetstream

    def jetstream(self) -> FakeJetStream:
        return self._jetstream


def test_consumer_validates_envelope_and_acks_only_after_handler():
    received: list[TaskEnvelope] = []
    consumer = TaskAdmittedConsumer(InMemoryTaskInbox(), received.append)
    message = FakeMessage(
        {
            "event_id": "event-1",
            "event_type": "task.admitted.v1",
            "schema_version": "1.0",
            "task": task_payload(),
        }
    )

    assert asyncio.run(consumer.handle(message)) is True

    assert received[0].task_id == "task-1"
    assert message.ack_count == 1


def test_consumer_deduplicates_redeliveries_by_jetstream_message_id():
    received: list[TaskEnvelope] = []
    consumer = TaskAdmittedConsumer(InMemoryTaskInbox(), received.append)
    first = FakeMessage(task_payload())
    duplicate = FakeMessage(task_payload())

    assert asyncio.run(consumer.handle(first)) is True
    assert asyncio.run(consumer.handle(duplicate)) is True

    assert len(received) == 1
    assert first.ack_count == 1
    assert duplicate.ack_count == 1


def test_consumer_releases_inbox_claim_when_handler_fails_so_nats_can_redeliver():
    attempts = 0

    def handler(_: TaskEnvelope) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("temporary agent failure")

    consumer = TaskAdmittedConsumer(InMemoryTaskInbox(), handler)
    message = FakeMessage(task_payload())

    with pytest.raises(RuntimeError, match="temporary"):
        asyncio.run(consumer.handle(message))
    assert message.ack_count == 0

    assert asyncio.run(consumer.handle(message)) is True
    assert attempts == 2
    assert message.ack_count == 1


def test_consumer_does_not_ack_a_concurrent_duplicate_while_first_delivery_is_in_flight():
    inbox = InMemoryTaskInbox()
    entered = asyncio.Event()
    release = asyncio.Event()

    async def handler(_: TaskEnvelope) -> None:
        entered.set()
        await release.wait()

    consumer = TaskAdmittedConsumer(inbox, handler)
    first = FakeMessage(task_payload())
    duplicate = FakeMessage(task_payload())

    async def exercise() -> tuple[bool, bool]:
        first_task = asyncio.create_task(consumer.handle(first))
        await entered.wait()
        duplicate_result = await consumer.handle(duplicate)
        release.set()
        first_result = await first_task
        return first_result, duplicate_result

    assert asyncio.run(exercise()) == (True, False)
    assert first.ack_count == 1
    assert duplicate.ack_count == 0


def test_sqlite_inbox_survives_consumer_restart_and_allows_failed_redelivery(tmp_path):
    inbox = SqliteTaskInbox(tmp_path / "trama.db", lease_ttl_seconds=30)

    assert inbox.claim("event-1") == "claimed"
    assert inbox.claim("event-1") == "in_flight"
    inbox.release("event-1")
    assert inbox.claim("event-1") == "claimed"
    inbox.complete("event-1")

    restarted = SqliteTaskInbox(tmp_path / "trama.db", lease_ttl_seconds=30)
    assert restarted.claim("event-1") == "duplicate"


def test_consumer_keeps_subscription_alive_for_a_transient_handler_failure():
    attempts = 0

    def handler(_: TaskEnvelope) -> None:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("retry me")

    first = FakeMessage(task_payload())
    redelivery = FakeMessage(task_payload())
    subscription = FakeSubscription([first, redelivery])
    jetstream = FakeJetStream(subscription)
    consumer = TaskAdmittedConsumer(InMemoryTaskInbox(), handler)

    asyncio.run(consumer.run(FakeConnection(jetstream)))

    assert attempts == 2
    assert first.ack_count == 0
    assert redelivery.ack_count == 1
    assert subscription.unsubscribed
    assert jetstream.arguments["subject"] == "trama.task.admitted.v1"
    assert jetstream.arguments["stream"] == "TRAMA_EVENTS"
    assert jetstream.arguments["durable"] == "trama-python-dispatch"
    assert jetstream.arguments["manual_ack"] is True
    assert jetstream.arguments["config"].max_deliver == 5
    assert jetstream.arguments["config"].ack_wait == 30.0
