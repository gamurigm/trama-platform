"""Consumidor durable de tareas admitidas por el gateway Go."""

from __future__ import annotations

import inspect
import json
import logging
from collections.abc import Awaitable, Callable, Mapping
from threading import RLock
from typing import Any, Literal, Protocol

from .contracts import TaskEnvelope

logger = logging.getLogger(__name__)

InboxDecision = Literal["claimed", "duplicate", "in_flight"]
TaskHandler = Callable[[TaskEnvelope], object | Awaitable[object]]


class JetStreamMessage(Protocol):
    data: bytes
    headers: Mapping[str, str] | None

    async def ack(self) -> None: ...


class TaskInbox(Protocol):
    def claim(self, event_id: str) -> InboxDecision: ...

    def complete(self, event_id: str) -> None: ...

    def release(self, event_id: str) -> None: ...


class InMemoryTaskInbox:
    """Inbox thread-safe para pruebas y ejecución local.

    En producción la misma interfaz debe estar respaldada por una tabla
    duradera. La decisión de no hacer ``ack`` mientras otro delivery está en
    curso evita perder un mensaje si la primera ejecución falla.
    """

    def __init__(self) -> None:
        self._completed: set[str] = set()
        self._in_flight: set[str] = set()
        self._lock = RLock()

    def claim(self, event_id: str) -> InboxDecision:
        with self._lock:
            if event_id in self._completed:
                return "duplicate"
            if event_id in self._in_flight:
                return "in_flight"
            self._in_flight.add(event_id)
            return "claimed"

    def complete(self, event_id: str) -> None:
        with self._lock:
            self._in_flight.discard(event_id)
            self._completed.add(event_id)

    def release(self, event_id: str) -> None:
        with self._lock:
            self._in_flight.discard(event_id)


class TaskAdmittedConsumer:
    """Valida, deduplica y entrega ``task.admitted.v1`` a Python."""

    def __init__(self, inbox: TaskInbox, handler: TaskHandler) -> None:
        self.inbox = inbox
        self.handler = handler

    async def handle(self, message: JetStreamMessage) -> bool:
        event_id = _event_id(message)
        decision = self.inbox.claim(event_id)
        if decision == "duplicate":
            await message.ack()
            return True
        if decision == "in_flight":
            return False

        try:
            task = _task_from_message(message.data)
            result = self.handler(task)
            if inspect.isawaitable(result):
                await result
        except BaseException:
            self.inbox.release(event_id)
            raise

        self.inbox.complete(event_id)
        await message.ack()
        return True

    async def run(
        self,
        connection: Any,
        *,
        subject: str = "trama.task.admitted.v1",
        stream: str = "TRAMA_EVENTS",
        durable: str = "trama-python-dispatch",
    ) -> None:
        """Consume JetStream messages until the subscription is cancelled.

        ``connection`` is deliberately duck-typed so unit tests do not need a
        live NATS server. With nats-py it is an ``nats.aio.client.Client``.
        """

        jetstream = connection.jetstream()
        subscription = await jetstream.subscribe(
            subject,
            stream=stream,
            durable=durable,
            manual_ack=True,
        )
        try:
            async for message in subscription.messages:
                try:
                    await self.handle(message)
                except Exception:
                    # No ack: JetStream will redeliver according to its
                    # consumer policy while this worker remains available.
                    logger.exception("task event delivery failed")
        finally:
            await subscription.unsubscribe()


def _event_id(message: JetStreamMessage) -> str:
    headers = message.headers or {}
    event_id = headers.get("Nats-Msg-Id") or headers.get("nats-msg-id")
    if not event_id:
        raise ValueError("task.admitted.v1 requires Nats-Msg-Id")
    return event_id


def _task_from_message(data: bytes) -> TaskEnvelope:
    payload = json.loads(data)
    if not isinstance(payload, dict):
        raise ValueError("task event payload must be an object")
    task_payload = payload.get("task", payload)
    if not isinstance(task_payload, dict):
        raise ValueError("task event must contain an object task")
    # Older gateway payloads omitted fields that Python can safely default.
    normalized = dict(task_payload)
    normalized.setdefault("schema_version", "1.0")
    normalized.setdefault("state", "accepted")
    return TaskEnvelope.model_validate(normalized)
