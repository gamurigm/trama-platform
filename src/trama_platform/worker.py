"""Proceso Python que consume las admisiones durables del gateway Go."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from typing import Any

from .coordination import build_coordination
from .nats_consumer import TaskAdmittedConsumer
from .runtime import TramaRuntime
from .settings import TramaSettings
from .state_store import PostgresTaskInbox, SqliteTaskInbox
from .storage import build_state_store

NatsConnect = Callable[..., Awaitable[Any]]


def run_task_worker(settings: TramaSettings) -> None:
    """Ejecuta el consumidor hasta una cancelación o desconexión."""

    asyncio.run(serve_task_worker(settings))


async def serve_task_worker(
    settings: TramaSettings,
    *,
    runtime: TramaRuntime | None = None,
    connection: Any | None = None,
    connect: NatsConnect | None = None,
) -> None:
    """Sirve tareas admitidas usando un runtime y conexión inyectables."""

    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    owns_runtime = runtime is None
    runtime_instance = runtime or TramaRuntime(
        coordination=build_coordination(settings),
        state_store=build_state_store(settings),
        queue_capacity=settings.queue_capacity,
        max_concurrency=settings.max_concurrency,
        dispatch_timeout_seconds=settings.dispatch_timeout_seconds,
        lease_seconds=settings.task_lease_seconds,
    )
    owns_connection = connection is None
    nats_connection = connection
    try:
        if nats_connection is None:
            if connect is None:
                import nats

                connect = nats.connect
            nats_connection = await connect(
                servers=[settings.nats_url],
                name=settings.nats_durable,
            )
        inbox = (
            PostgresTaskInbox(settings.database_url)
            if settings.database_url
            else SqliteTaskInbox(settings.state_path)
        )
        consumer = TaskAdmittedConsumer(inbox, runtime_instance.accept_admitted_task)
        await consumer.run(
            nats_connection,
            subject=settings.nats_subject,
            stream=settings.nats_stream,
            durable=settings.nats_durable,
            ack_wait_seconds=settings.nats_ack_wait_seconds,
            max_deliver=settings.nats_max_deliver,
        )
    finally:
        if owns_connection and nats_connection is not None:
            await nats_connection.drain()
        if owns_runtime:
            runtime_instance.close()
