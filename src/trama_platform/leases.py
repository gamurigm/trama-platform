"""Ownership duradero de tareas entre réplicas del control plane."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from threading import Event, Lock, Thread, current_thread
from typing import Protocol
from uuid import uuid4

from .contracts import TaskEnvelope


@dataclass(frozen=True, slots=True)
class TaskLease:
    """Token de ownership de una tarea dentro de un namespace."""

    organization_id: str
    task_id: str
    owner_id: str
    lease_token: str
    attempt: int
    expires_at: datetime


class TaskLeaseStore(Protocol):
    """Operaciones atómicas requeridas por el manager de leases."""

    def claim_task(
        self,
        task: TaskEnvelope,
        *,
        owner_id: str,
        lease_seconds: int,
    ) -> TaskLease | None: ...

    def renew_task_lease(self, lease: TaskLease, *, lease_seconds: int) -> bool: ...

    def complete_task_lease(self, lease: TaskLease) -> bool: ...

    def complete_task_lease_for_task(self, organization_id: str, task_id: str) -> bool: ...

    def release_task_lease(self, lease: TaskLease) -> bool: ...


@dataclass(slots=True)
class _Renewal:
    lease: TaskLease
    stop: Event
    thread: Thread


class TaskLeaseManager:
    """Coordina claim y renovación local de leases duraderos."""

    def __init__(self, store: TaskLeaseStore, *, owner_id: str, lease_seconds: int) -> None:
        if not owner_id.strip():
            raise ValueError("owner_id es obligatorio")
        if lease_seconds < 1:
            raise ValueError("lease_seconds debe ser mayor que cero")
        self.store = store
        self.owner_id = owner_id
        self.lease_seconds = lease_seconds
        self._lock = Lock()
        self._active: dict[tuple[str, str], _Renewal] = {}
        self._closed = False

    def claim(self, task: TaskEnvelope) -> TaskLease | None:
        with self._lock:
            if self._closed:
                raise RuntimeError("el manager de leases esta cerrado")
        return self.store.claim_task(
            task,
            owner_id=self.owner_id,
            lease_seconds=self.lease_seconds,
        )

    def start_renewal(self, lease: TaskLease) -> None:
        key = self._key(lease.organization_id, lease.task_id)
        with self._lock:
            if self._closed or key in self._active:
                return
            stop = Event()
            thread = Thread(
                target=self._renew_until_stopped,
                args=(lease, stop),
                name=f"trama-lease-renew-{lease.task_id}",
                daemon=True,
            )
            self._active[key] = _Renewal(lease=lease, stop=stop, thread=thread)
            thread.start()

    def complete(self, task: TaskEnvelope) -> bool:
        self._stop_local(task.organization_id, task.task_id)
        return self.store.complete_task_lease_for_task(task.organization_id, task.task_id)

    def release(self, lease: TaskLease) -> bool:
        self._stop_local(lease.organization_id, lease.task_id, lease.lease_token)
        return self.store.release_task_lease(lease)

    def close(self) -> None:
        with self._lock:
            if self._closed:
                return
            self._closed = True
            renewals = list(self._active.values())
            self._active.clear()
        for renewal in renewals:
            renewal.stop.set()
            if renewal.thread is not current_thread():
                renewal.thread.join(timeout=1)

    def _renew_until_stopped(self, lease: TaskLease, stop: Event) -> None:
        interval = max(0.2, self.lease_seconds / 3)
        while not stop.wait(interval):
            if not self.store.renew_task_lease(lease, lease_seconds=self.lease_seconds):
                self._remove_if_current(lease)
                return

    def _stop_local(
        self, organization_id: str, task_id: str, lease_token: str | None = None
    ) -> None:
        key = self._key(organization_id, task_id)
        with self._lock:
            renewal = self._active.get(key)
            if renewal is None or (
                lease_token is not None and renewal.lease.lease_token != lease_token
            ):
                return
            self._active.pop(key, None)
        renewal.stop.set()
        if renewal.thread is not current_thread():
            renewal.thread.join(timeout=1)

    def _remove_if_current(self, lease: TaskLease) -> None:
        key = self._key(lease.organization_id, lease.task_id)
        with self._lock:
            renewal = self._active.get(key)
            if renewal is not None and renewal.lease.lease_token == lease.lease_token:
                self._active.pop(key, None)

    @staticmethod
    def _key(organization_id: str, task_id: str) -> tuple[str, str]:
        return organization_id, task_id


def new_owner_id() -> str:
    """Genera un owner efímero sin exponer información sensible."""

    return f"trama-worker-{uuid4().hex}"
