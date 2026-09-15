# Núcleo Python con cola y backpressure Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Añadir al núcleo Python de TRAMA una cola bounded, despacho concurrente controlado, backpressure HTTP y recuperación durable de tareas sin cambiar REST, MCP ni los contratos v1.0.

**Architecture:** TramaRuntime seguirá validando namespaces y siendo el orquestador de estado. Un TaskDispatcher independiente reservará capacidad, persistirá la admisión mediante callbacks del runtime, pondrá tareas en una cola thread-safe y las enviará a CoordinationPort mediante workers fijos. SqliteStateStore seguirá siendo el adaptador local detrás de StateStorePort; esta fase no introduce PostgreSQL, Redis, NATS, GraphQL ni Go.

**Tech Stack:** Python 3.12, queue.Queue, threading, FastAPI, Pydantic 2, SQLite existente, pytest y Ruff.

**Spec:** docs/superpowers/specs/2026-09-15-python-core-queueing-design.md

## Global Constraints

- REST, MCP stdio, contratos Pydantic y esquemas JSON versionados en 1.0 se conservan.
- TramaRuntime y el estado persistido son la fuente única de verdad; la cola en memoria solo representa trabajo pendiente.
- La validación de organización, proyecto y repositorio sucede antes de reservar capacidad y antes de llamar a CoordinationPort.
- Una admisión HTTP 202 requiere validación, reserva de capacidad, persistencia de la tarea y evento de admisión.
- Una cola sin capacidad responde HTTP 429 con código queue_full; no persiste ni despacha esa tarea.
- SqliteStateStore es únicamente el adaptador local de esta fase y permanece detrás de StateStorePort.
- Los defaults son TRAMA_QUEUE_CAPACITY=100, TRAMA_MAX_CONCURRENCY=4 y TRAMA_DISPATCH_TIMEOUT_SECONDS=900.
- No se añaden Gateway Go, GraphQL, Redis, NATS, PostgreSQL, cron, ejecución remota ni nuevas herramientas MCP.
- No se escriben secretos, tokens, cookies, credenciales ni argumentos completos del coordinador en contratos, eventos, logs o documentación.
- Todos los workers deben detenerse de forma idempotente; pytest se ejecuta con .\\.venv\\Scripts\\python.exe -m pytest y Ruff con .\\.venv\\Scripts\\python.exe -m ruff check .
- Se preservan los cambios locales existentes en AGENTS.md y refact1.md; no se incluyen en ningún commit de este plan.

---

### Task 1: Cola bounded y dispatcher thread-safe

**Files:**
- Create: src/trama_platform/queueing.py
- Modify: src/trama_platform/ports.py, sección de puertos de coordinación
- Create: tests/test_queueing.py

**Interfaces:**
- TaskQueuePort.put(task: TaskEnvelope) -> None, get(timeout: float | None = None) -> TaskEnvelope | None, task_done() -> None, qsize() -> int, capacity: int y close() -> None.
- BoundedTaskQueue(capacity: int) implementa TaskQueuePort con queue.Queue y rechaza capacidades no positivas.
- QueueCapacityError representa falta de capacidad; DispatcherClosedError representa un dispatcher cerrado.
- TaskDispatcher.submit(task: TaskEnvelope, persist: Callable[[], None]) -> str reserva capacidad, persiste y publica la tarea.
- TaskDispatcher.recover(tasks: Sequence[TaskEnvelope]) -> None reencola tareas persistidas sin duplicar eventos.
- TaskDispatcher.status() -> dict[str, object] devuelve queue_depth, queue_capacity, active_dispatches, max_concurrency y dispatcher_status.
- TaskDispatcher.wait_for_idle(timeout: float) -> bool es un helper local de pruebas; close() -> None detiene workers de forma idempotente.

- [ ] Step 1: Write the failing test

Crear tests/test_queueing.py con una tarea válida, una coordinación bloqueable y estas expectativas:

~~~python
def test_bounded_queue_rejects_the_item_over_capacity():
    queue = BoundedTaskQueue(capacity=1)
    queue.put(make_task("task-1"))
    with pytest.raises(QueueCapacityError):
        queue.put(make_task("task-2"))


def test_dispatcher_never_runs_more_than_configured_workers():
    blocking_coordination = BlockingCoordination()
    dispatcher = TaskDispatcher(
        blocking_coordination,
        queue_capacity=4,
        max_concurrency=2,
        transition=lambda *args: None,
        current_task=lambda task_id: make_task(task_id),
    )
    try:
        for index in range(4):
            dispatcher.submit(make_task(f"task-{index}"), persist=lambda: None)
        assert blocking_coordination.started.wait(timeout=2)
        blocking_coordination.release.set()
        assert dispatcher.wait_for_idle(timeout=2)
        assert blocking_coordination.peak <= 2
    finally:
        dispatcher.close()


def test_dispatcher_releases_reservation_when_persistence_fails():
    dispatcher = TaskDispatcher(
        RecordingCoordination(),
        queue_capacity=1,
        max_concurrency=1,
        transition=lambda *args: None,
        current_task=lambda task_id: make_task(task_id),
    )
    try:
        with pytest.raises(RuntimeError, match="persist failed"):
            dispatcher.submit(
                make_task("task-1"),
                persist=lambda: (_ for _ in ()).throw(RuntimeError("persist failed")),
            )
        dispatcher.submit(make_task("task-2"), persist=lambda: None)
    finally:
        dispatcher.close()
~~~

Definir en el mismo archivo los helpers make_task, BlockingCoordination y RecordingCoordination. La coordinación bloqueable debe contar active y peak bajo un Lock, señalizar started, esperar un Event release y disminuir active al terminar.

- [ ] Step 2: Run tests to verify they fail

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_queueing.py -q

Expected: FAIL porque no existen BoundedTaskQueue, QueueCapacityError, TaskDispatcher ni TaskQueuePort.

- [ ] Step 3: Write minimal implementation

Añadir TaskQueuePort a ports.py y crear queueing.py con este constructor:

~~~python
TaskDispatcher(
    coordination: CoordinationPort,
    *,
    queue_capacity: int,
    max_concurrency: int,
    transition: Callable[[TaskEnvelope, str, str, dict[str, object]], None],
    current_task: Callable[[str], TaskEnvelope | None],
    dispatch_timeout_seconds: int = 900,
    queue: TaskQueuePort | None = None,
)
~~~

Usar queue.Queue(maxsize=queue_capacity), BoundedSemaphore(queue_capacity + max_concurrency), un contador activo protegido por lock y threads daemon nombrados trama-dispatcher-<n>. submit adquiere el semáforo, ejecuta persist, pone la tarea con put_nowait y libera la reserva ante cualquier excepción. close impide nuevas admisiones, inserta sentinelas, espera el timeout y deja el estado closed; durante el drenaje usa draining.

Cada worker consulta current_task antes de despachar, ignora una tarea ya cancelled, persiste state=running mediante transition, llama a coordination.submit_task y libera la reserva en finally. Si el coordinador falla, llama a transition con state=failed, acción task.dispatch, estado de evento failed y solamente error_type y mensaje truncado/sanitizado. recover usa la misma reserva y cola sin llamar al callback de persistencia. Validar queue_capacity >= 1, max_concurrency >= 1 y dispatch_timeout_seconds >= 1.

- [ ] Step 4: Run tests to verify they pass

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_queueing.py -q

Expected: PASS, incluyendo rechazo de capacidad, máximo de dos workers y rollback de una persistencia fallida.

- [ ] Step 5: Commit

~~~powershell
git add src/trama_platform/ports.py src/trama_platform/queueing.py tests/test_queueing.py
git commit -m "feat: add bounded task dispatcher"
~~~

### Task 2: Integración con runtime y persistencia durable local

**Files:**
- Modify: src/trama_platform/ports.py, contrato StateStorePort
- Modify: src/trama_platform/state_store.py, operaciones de escritura
- Modify: src/trama_platform/runtime.py, constructor y ciclo de tareas
- Modify: tests/test_runtime.py
- Modify: tests/test_state_store.py

**Interfaces:**
- StateStorePort.save_task_transition(task: TaskEnvelope, event: OperationEvent) -> None persiste una tarea y su evento de transición.
- SqliteStateStore.save_task_transition escribe state_records y operation_events usando una misma transacción SQLite.
- TramaRuntime(..., queue_capacity: int = 100, max_concurrency: int = 4, dispatch_timeout_seconds: int = 900) crea un dispatcher configurable.
- TramaRuntime.submit_task(task: TaskEnvelope) -> str valida, aplica idempotencia, admite y persiste antes de devolver el id.
- TramaRuntime.status() conserva sus campos y añade las métricas del dispatcher; close() -> None es idempotente.

- [ ] Step 1: Write the failing test

Añadir pruebas con coordinación grabable y bloqueable:

~~~python
def test_runtime_persists_task_before_dispatch(tmp_path):
    coordination = RecordingCoordination()
    store = SqliteStateStore(tmp_path / "trama.db")
    runtime = TramaRuntime(
        coordination=coordination,
        state_store=store,
        queue_capacity=1,
        max_concurrency=1,
    )
    try:
        runtime.register_project(manifest())
        assert runtime.submit_task(task("task-1")) == "task-1"
        assert runtime.wait_for_idle(timeout=2)
        assert coordination.seen == ["task-1"]
        assert [item.task_id for item in store.load_tasks()] == ["task-1"]
    finally:
        runtime.close()


def test_runtime_does_not_mutate_state_when_capacity_is_exhausted():
    runtime, coordination = runtime_with_blocking_coordination(
        queue_capacity=1,
        max_concurrency=1,
    )
    try:
        runtime.register_project(manifest())
        runtime.submit_task(task("task-1"))
        runtime.submit_task(task("task-2"))
        with pytest.raises(QueueCapacityError):
            runtime.submit_task(task("task-3"))
        assert "task-3" not in runtime.tasks
    finally:
        coordination.release.set()
        runtime.close()
~~~

Completar con una prueba donde el coordinador falla y deja state=failed más un evento task.dispatch; una repetición idéntica de task_id no encola ni registra dos veces; una configuración distinta se rechaza; una tarea cancelada antes de ser tomada no llega al coordinador; y un running persistido se normaliza a accepted y se recupera. En tests/test_state_store.py, guardar una transición y comprobar mediante load_tasks() y list_events() que ambas partes quedan presentes.

Definir en tests/test_runtime.py los helpers task(task_id) y runtime_with_blocking_coordination(queue_capacity, max_concurrency) con organización org-a, proyecto demo y repositorio repo-a; reutilizar manifest() existente. El helper de runtime debe devolver también la coordinación bloqueable para que la prueba libere sus Events antes de close().

- [ ] Step 2: Run tests to verify they fail

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_runtime.py tests/test_state_store.py -q

Expected: FAIL porque el runtime despacha directamente a CoordinationPort, no tiene cola/cierre y StateStorePort no tiene persistencia de transición.

- [ ] Step 3: Write minimal implementation

Crear el dispatcher después de cargar proyectos/tareas y conectar callbacks privados del runtime. En submit_task, validar organización/proyecto/repositorio, comparar identidad ignorando solo state y created_at, reservar mediante TaskDispatcher.submit y persistir accepted más task.submit antes de publicar. Una tarea idéntica ya existente devolverá su id sin duplicar cola ni evento.

El callback de transición actualizará self.tasks, guardará la tarea y el evento mediante save_task_transition, y usará estados de evento compatibles con OperationEvent (accepted, succeeded, failed, blocked). Mantener InMemoryCoordination.tasks sincronizado al admitir una tarea. record_result actualizará la tarea, guardará resultado/evento y conservará las validaciones existentes. cancel_task marcará la tarea; el worker volverá a comprobarla. retry_task pedirá capacidad antes de persistir accepted, de modo que una cola llena conserve el estado previo.

Durante la recuperación, normalizar y guardar como accepted las tareas running, pasar las tareas admitidas a recover y no crear eventos task.submit duplicados. wait_for_idle delegará en el dispatcher. close será seguro si se llama repetidamente.

En SqliteStateStore, extraer una operación que reciba una conexión abierta y escriba state_records de la tarea y operation_events en una sola transacción. Conservar save_task y append_event para consumidores existentes.

- [ ] Step 4: Run tests to verify they pass

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_runtime.py tests/test_state_store.py -q

Expected: PASS, incluyendo namespaces, promociones, SQLite, eventos y lifecycle existente.

- [ ] Step 5: Commit

~~~powershell
git add src/trama_platform/ports.py src/trama_platform/state_store.py src/trama_platform/runtime.py tests/test_runtime.py tests/test_state_store.py
git commit -m "feat: dispatch runtime tasks through bounded queue"
~~~

### Task 3: Configuración, API de backpressure y shutdown

**Files:**
- Modify: src/trama_platform/settings.py
- Modify: src/trama_platform/api.py
- Modify: src/trama_platform/cli.py
- Modify: .env.example
- Modify: README.md
- Modify: docs/ARQUITECTURA.md
- Modify: tests/test_settings.py
- Modify: tests/test_api.py
- Modify: tests/test_cli_gateway.py

**Interfaces:**
- TramaSettings.queue_capacity, max_concurrency y dispatch_timeout_seconds provienen de TRAMA_QUEUE_CAPACITY, TRAMA_MAX_CONCURRENCY y TRAMA_DISPATCH_TIMEOUT_SECONDS.
- create_app(..., settings: TramaSettings | None = None) -> FastAPI pasa los límites al runtime creado automáticamente.
- Submit y retry convierten QueueCapacityError en HTTP 429, detalle {"code": "queue_full", "message": "La cola de tareas está llena"} y header Retry-After: 1.
- GET /v1/status añade queue_depth, queue_capacity, active_dispatches, max_concurrency y dispatcher_status.
- El lifespan de FastAPI llama runtime.close() al apagar la app; la rama trama api pasa TramaSettings a create_app.

- [ ] Step 1: Write the failing test

En tests/test_settings.py, añadir defaults 100/4/900 y parametrizar "0", "-1" y "not-an-int" para las tres variables, esperando ValueError con el nombre de la variable. En tests/test_api.py, inyectar un runtime de capacidad 1+1 con coordinación bloqueable, comprobar 429, código queue_full, Retry-After: 1, ausencia de la tarea rechazada y los cinco campos de status. Añadir shutdown repetido sin excepción.

En tests/test_cli_gateway.py, comprobar que la rama api pasa los tres campos de TramaSettings al runtime/app y que config get --json los expone sin secretos.

- [ ] Step 2: Run tests to verify they fail

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_settings.py tests/test_api.py tests/test_cli_gateway.py -q

Expected: FAIL porque las variables no están en TramaSettings, la API no captura QueueCapacityError, status no tiene métricas de cola y shutdown no cierra el runtime.

- [ ] Step 3: Write minimal implementation

Añadir un lector de entero positivo conservando el error de entero inválido y estos valores exactos:

~~~python
queue_capacity=_read_positive_int("TRAMA_QUEUE_CAPACITY", 100),
max_concurrency=_read_positive_int("TRAMA_MAX_CONCURRENCY", 4),
dispatch_timeout_seconds=_read_positive_int("TRAMA_DISPATCH_TIMEOUT_SECONDS", 900),
~~~

Actualizar create_app con settings keyword-only; cuando no haya runtime inyectado, construirlo con esos límites. En submit y retry capturar solo QueueCapacityError y devolver HTTPException(status_code=429, detail={"code": "queue_full", "message": "La cola de tareas está llena"}, headers={"Retry-After": "1"}), conservando los 404/409 actuales. Añadir lifespan idempotente y pasar settings desde cli.py.

Actualizar .env.example, config get, README y docs/ARQUITECTURA.md para explicar la capacidad máxima queue_capacity + max_concurrency, el 429 esperado y que la cola es local al proceso. Conservar la documentación existente de API, MCP, CCCC y Hermes.

- [ ] Step 4: Run tests to verify they pass

Run: .\\.venv\\Scripts\\python.exe -m pytest tests/test_settings.py tests/test_api.py tests/test_cli_gateway.py -q

Expected: PASS, incluidos los tests previos de CLI, CCCC, Hermes, API, lifecycle y aislamiento.

- [ ] Step 5: Commit

~~~powershell
git add .env.example README.md docs/ARQUITECTURA.md src/trama_platform/settings.py src/trama_platform/api.py src/trama_platform/cli.py tests/test_settings.py tests/test_api.py tests/test_cli_gateway.py
git commit -m "feat: expose task queue backpressure"
~~~

### Task 4: Verificación completa y entrega

**Files:**
- Modify: únicamente archivos requeridos por un fallo de verificación de Tasks 1-3.
- Test: tests/test_queueing.py, tests/test_runtime.py, tests/test_state_store.py, tests/test_settings.py, tests/test_api.py, tests/test_cli_gateway.py.

**Interfaces:**
- Los contratos públicos actuales continúan exportándose sin cambios de esquema.
- El smoke local muestra API ready, métricas de cola y MCP stdio con exactamente cinco herramientas.

- [ ] Step 1: Run the complete verification commands

Run, en este orden:

~~~powershell
.\\.venv\\Scripts\\python.exe -m trama_platform export-schemas contracts
.\\.venv\\Scripts\\python.exe -m pytest
.\\.venv\\Scripts\\python.exe -m ruff check .
git diff --check
~~~

Expected: todos los comandos salen con código 0, las nuevas pruebas pasan y los esquemas versionados no cambian.

- [ ] Step 2: Run the local API and MCP smoke check

Iniciar la API en 127.0.0.1:8090, consultar /v1/status y confirmar queue_depth, queue_capacity, active_dispatches, max_concurrency y dispatcher_status. Iniciar después trama mcp --api-url http://127.0.0.1:8090 con el cliente oficial MCP y verificar exactamente trama_register_project, trama_search_context, trama_submit_task, trama_record_result y trama_capture_memory. Detener únicamente los procesos iniciados y comprobar que 8090 deja de responder.

- [ ] Step 3: Review repository state

Run: git status --short --branch, git log --oneline -8, git diff --stat origin/main...HEAD, git diff --check

Confirmar que los commits solo contienen dispatcher, integración, configuración/documentación y pruebas. Reportar por separado AGENTS.md y refact1.md; no agregarlos, modificarlos ni borrarlos.

- [ ] Step 4: Commit verification adjustments if required

Si una verificación exige un ajuste, añadir solo el archivo afectado y usar un mensaje específico como fix: address queue verification finding. Si toda la verificación pasa, no crear un commit vacío.
