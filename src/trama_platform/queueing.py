"""Cola local y dispatcher acotado para tareas de TRAMA."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from queue import Empty, Full, Queue
from threading import BoundedSemaphore, Condition, Event, Lock, Thread
from time import monotonic

from .contracts import TaskEnvelope
from .leases import TaskLease, TaskLeaseManager
from .ports import CoordinationPort, TaskQueuePort


class QueueCapacityError(RuntimeError):
    """La instancia no tiene capacidad para admitir otra tarea."""


class DispatcherClosedError(RuntimeError):
    """El dispatcher ya no acepta nuevas tareas."""


class BoundedTaskQueue(TaskQueuePort):
    """Implementación thread-safe de una cola bounded local."""

    def __init__(self, capacity: int) -> None:
        if capacity < 1:
            raise ValueError("queue_capacity debe ser mayor que cero")
        self.capacity = capacity
        self._items: Queue[TaskEnvelope] = Queue(maxsize=capacity)
        self._closed = Event()

    def put(self, task: TaskEnvelope) -> None:
        if self._closed.is_set():
            raise DispatcherClosedError("La cola de tareas esta cerrada")
        try:
            self._items.put_nowait(task)
        except Full as exc:
            raise QueueCapacityError("La cola de tareas esta llena") from exc

    def get(self, timeout: float | None = None) -> TaskEnvelope | None:
        deadline = None if timeout is None else monotonic() + timeout
        while True:
            if self._closed.is_set() and self._items.empty():
                return None
            wait = 0.1
            if deadline is not None:
                wait = min(wait, max(0.0, deadline - monotonic()))
                if wait == 0.0:
                    raise Empty
            try:
                return self._items.get(timeout=wait)
            except Empty:
                if deadline is not None and monotonic() >= deadline:
                    raise

    def task_done(self) -> None:
        self._items.task_done()

    def qsize(self) -> int:
        return self._items.qsize()

    def close(self) -> None:
        self._closed.set()


TaskTransition = Callable[[TaskEnvelope, str, str, dict[str, object]], bool | None]
TaskLookup = Callable[[str, str], TaskEnvelope | None]


class TaskDispatcher:
    """Despacha tareas a un coordinador con backpressure local."""

    def __init__(
        self,
        coordination: CoordinationPort,
        *,
        queue_capacity: int,
        max_concurrency: int,
        transition: TaskTransition,
        current_task: TaskLookup,
        dispatch_timeout_seconds: int = 900,
        queue: TaskQueuePort | None = None,
        lease_manager: TaskLeaseManager | None = None,
    ) -> None:
        if queue_capacity < 1:
            raise ValueError("queue_capacity debe ser mayor que cero")
        if max_concurrency < 1:
            raise ValueError("max_concurrency debe ser mayor que cero")
        if dispatch_timeout_seconds < 1:
            raise ValueError("dispatch_timeout_seconds debe ser mayor que cero")
        self.coordination = coordination
        self.queue = queue or BoundedTaskQueue(queue_capacity)
        self.max_concurrency = max_concurrency
        self.dispatch_timeout_seconds = dispatch_timeout_seconds
        self._transition = transition
        self._current_task = current_task
        self.lease_manager = lease_manager
        self._reservations = BoundedSemaphore(queue_capacity + max_concurrency)
        self._lock = Lock()
        self._idle = Condition(self._lock)
        self._active_dispatches = 0
        self._status = "running"
        self._threads: list[Thread] = []
        self._start_workers()

    def _start_workers(self) -> None:
        for index in range(self.max_concurrency):
            thread = Thread(
                target=self._worker,
                name=f"trama-dispatcher-{index + 1}",
                daemon=True,
            )
            self._threads.append(thread)
            thread.start()

    def _reserve(self) -> None:
        with self._lock:
            if self._status != "running":
                raise DispatcherClosedError("El dispatcher de tareas no esta activo")
        if not self._reservations.acquire(blocking=False):
            raise QueueCapacityError("La capacidad de tareas esta agotada")

    def submit(self, task: TaskEnvelope, persist: Callable[[], None]) -> str:
        self._reserve()
        try:
            persist()
            self.queue.put(task)
        except Exception:
            self._reservations.release()
            raise
        return task.task_id

    def recover(self, tasks: Sequence[TaskEnvelope]) -> None:
        for task in tasks:
            try:
                self._reserve()
                self.queue.put(task)
            except QueueCapacityError:
                self._reservations.release()
                return
            except Exception:
                self._reservations.release()
                raise

    def _worker(self) -> None:
        while True:
            try:
                task = self.queue.get(timeout=None)
            except Empty:
                continue
            if task is None:
                return
            with self._idle:
                self._active_dispatches += 1
            lease: TaskLease | None = None
            try:
                current = self._current_task(task.organization_id, task.task_id)
                if current is None or current.state not in {"accepted", "running"}:
                    continue
                if self.lease_manager is not None:
                    lease = self.lease_manager.claim(current)
                    if lease is None:
                        continue
                    self.lease_manager.start_renewal(lease)
                updates: dict[str, object] = {"state": "running"}
                if lease is not None:
                    updates["execution_attempt"] = lease.attempt
                running = current.model_copy(update=updates)
                try:
                    transitioned = self._transition(running, "task.dispatch", "accepted", {})
                    if transitioned is False:
                        if lease is not None:
                            self.lease_manager.release(lease)
                        continue
                    if lease is not None and not self.lease_manager.is_current(lease):
                        self.lease_manager.release(lease)
                        continue
                    self.coordination.submit_task(running)
                except Exception as exc:
                    failed = running.model_copy(update={"state": "failed"})
                    try:
                        self._transition(
                            failed,
                            "task.dispatch",
                            "failed",
                            {
                                "error_type": type(exc).__name__,
                                "message": str(exc)[:500],
                            },
                        )
                    finally:
                        if lease is not None:
                            self.lease_manager.release(lease)
            finally:
                with self._idle:
                    self._active_dispatches -= 1
                    self._idle.notify_all()
                self._reservations.release()
                self.queue.task_done()

    def complete_task_lease(self, task: TaskEnvelope) -> bool:
        if self.lease_manager is None:
            return False
        return self.lease_manager.complete(task)

    def wait_for_idle(self, timeout: float) -> bool:
        deadline = monotonic() + timeout
        with self._idle:
            while self.queue.qsize() or self._active_dispatches:
                remaining = deadline - monotonic()
                if remaining <= 0:
                    return False
                self._idle.wait(timeout=remaining)
            return True

    def status(self) -> dict[str, object]:
        with self._lock:
            status = self._status
            active = self._active_dispatches
        return {
            "queue_depth": self.queue.qsize(),
            "queue_capacity": self.queue.capacity,
            "active_dispatches": active,
            "max_concurrency": self.max_concurrency,
            "dispatcher_status": status,
        }

    def close(self) -> None:
        with self._lock:
            if self._status == "closed":
                return
            self._status = "draining"
        self.queue.close()
        deadline = monotonic() + self.dispatch_timeout_seconds
        for thread in self._threads:
            remaining = max(0.0, deadline - monotonic())
            thread.join(timeout=remaining)
        if self.lease_manager is not None:
            self.lease_manager.close()
        with self._lock:
            self._status = "closed"
