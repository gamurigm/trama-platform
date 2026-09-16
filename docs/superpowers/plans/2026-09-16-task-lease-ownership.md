# Ownership distribuido de tareas Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Garantizar que una sola réplica reclame una tarea por vez, que el
worker propietario pueda renovar su lease y que una réplica posterior recupere
la tarea cuando el lease expire.

**Architecture:** Se añade un contrato interno `TaskLease` y un
`TaskLeaseManager` que encapsula claim, renovación y finalización. SQLite y
Postgres implementan operaciones atómicas sobre una tabla namespace-aware; el
dispatcher reclama antes de despachar y el runtime finaliza el lease al
persistir un resultado terminal.

**Tech Stack:** Python 3.12, dataclasses, SQLite, psycopg 3, PostgreSQL,
pytest, Ruff y migraciones SQL versionadas.

**Spec:** `docs/superpowers/specs/2026-09-16-task-lease-ownership-design.md`

## Global Constraints

- El namespace de cada lease es `(organization_id, task_id)`.
- Los tokens de lease nunca se imprimen ni se persisten fuera de la tabla de leases.
- No se modifica `TaskEnvelope` ni la API pública/MCP.
- No se crean ni versionan `settings.json`, `.env`, `.vscode` ni credenciales.
- SQLite mantiene el comportamiento local; Postgres es obligatorio para el modo distribuido.
- La entrega NATS continúa siendo at-least-once y CCCC no se presenta como exactly-once.
- Cada tarea termina con una prueba ejecutable y un commit explícito.

---

### Task 1: Contrato interno y ciclo de renovación

**Files:**
- Create: `src/trama_platform/leases.py`
- Modify: `src/trama_platform/ports.py`
- Test: `tests/test_leases.py`

**Interfaces:**
- Consumes: `TaskEnvelope` y un almacenamiento que implemente las operaciones de lease.
- Produces: `TaskLease`, `TaskLeaseStore` y `TaskLeaseManager` para el dispatcher y el runtime.

- [ ] **Step 1: Write the failing test**

Crear `tests/test_leases.py` con un store falso thread-safe que registre las
operaciones y comprobar:

```python
def test_manager_claims_and_completes_a_task_once():
    store = RecordingLeaseStore()
    manager = TaskLeaseManager(store, owner_id="worker-a", lease_seconds=30)

    lease = manager.claim(task("task-1"))

    assert lease is not None
    assert lease.owner_id == "worker-a"
    assert manager.complete(task("task-1")) is True
    assert store.completed == [lease]
```

Añadir también la aserción de que un `TaskLeaseManager` exige `lease_seconds >= 1` y
que `manager.claim` devuelve `None` cuando el store informa que otro owner
mantiene un lease activo.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_leases.py -q`

Expected: FAIL porque `TaskLeaseManager` y `TaskLeaseStore` todavía no
existen.

- [ ] **Step 3: Write minimal implementation**

Implement en `leases.py`:

```python
@dataclass(frozen=True, slots=True)
class TaskLease:
    organization_id: str
    task_id: str
    owner_id: str
    lease_token: str
    attempt: int
    expires_at: datetime

class TaskLeaseStore(Protocol):
    def claim_task(self, task: TaskEnvelope, *, owner_id: str, lease_seconds: int) -> TaskLease | None: ...
    def renew_task_lease(self, lease: TaskLease, *, lease_seconds: int) -> bool: ...
    def complete_task_lease(self, lease: TaskLease) -> bool: ...
    def complete_task_lease_for_task(self, organization_id: str, task_id: str) -> bool: ...
    def release_task_lease(self, lease: TaskLease) -> bool: ...
```

`TaskLeaseManager` validará el owner/token, mantendrá los leases activos en
memoria para renovar cada `max(1, lease_seconds // 3)` segundos y detendrá
cada hilo de renovación en `complete`, `release` y `close`. La finalización
por tarea se usará únicamente después de validar y persistir un resultado
terminal en el runtime.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_leases.py -q`

Expected: PASS con todas las pruebas del manager.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_leases.py src/trama_platform/leases.py src/trama_platform/ports.py
git commit -m "feat: definir contrato de leases de tareas"
```

### Task 2: Persistencia atómica en SQLite y Postgres

**Files:**
- Create: `gateway/migrations/000004_task_leases.sql`
- Modify: `src/trama_platform/state_store.py`
- Test: `tests/test_state_store_leases.py`

**Interfaces:**
- Consumes: `TaskLeaseStore` y `TaskLease` de Task 1.
- Produces: Implementaciones duraderas de claim, renew, complete y release para ambos backends.

- [ ] **Step 1: Write the failing test**

Crear pruebas con dos owners sobre el mismo `SqliteStateStore`:

```python
import time

def test_sqlite_claim_is_exclusive_and_expired_lease_can_be_reclaimed(tmp_path):
    store = SqliteStateStore(tmp_path / "trama.db")
    item = task("task-1", organization_id="org-a")

    first = store.claim_task(item, owner_id="worker-a", lease_seconds=1)
    second = store.claim_task(item, owner_id="worker-b", lease_seconds=1)

    assert first is not None
    assert second is None

    time.sleep(1.1)
    reclaimed = store.claim_task(item, owner_id="worker-b", lease_seconds=1)

    assert reclaimed is not None
    assert reclaimed.owner_id == "worker-b"
    assert reclaimed.attempt == first.attempt + 1
```

Probar también token incorrecto para renovar/completar, `release` que deja
la fila inmediatamente reclamable y `complete_task_lease_for_task` que cierra
el lease activo del namespace correcto.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_state_store_leases.py -q`

Expected: FAIL porque las tablas y métodos todavía no existen.

- [ ] **Step 3: Write minimal implementation**

Añadir la tabla `trama.task_leases` y su equivalente SQLite con clave primaria
`(organization_id, task_id)`, owner, token, attempt, `claimed_at`,
`expires_at` y `completed`. Implementar claim con `INSERT ... ON CONFLICT ...
WHERE completed OR expires_at <= now`, de modo que una única transacción
pueda reclamar la tarea. Renovar y completar deberán filtrar por namespace,
owner y token. El método por tarea filtrará por namespace y solo marcará como
completado un lease activo.

Registrar la migración 4 en `schema_migrations`, añadir índices para leases
activos/vencidos y mantener el commit/rollback de cada operación existente.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_state_store_leases.py tests/test_production_storage.py -q`

Expected: PASS; además `git diff --check` no debe reportar whitespace.

- [ ] **Step 5: Commit**

```powershell
git add gateway/migrations/000004_task_leases.sql src/trama_platform/state_store.py tests/test_state_store_leases.py
git commit -m "feat: persistir leases namespace-aware en los stores"
```

### Task 3: Integrar leases con dispatcher y runtime

**Files:**
- Modify: `src/trama_platform/queueing.py`
- Modify: `src/trama_platform/runtime.py`
- Modify: `src/trama_platform/settings.py`
- Modify: `src/trama_platform/api.py`
- Test: `tests/test_runtime.py`
- Test: `tests/test_settings.py`

**Interfaces:**
- Consumes: `TaskLeaseManager` y las implementaciones de Task 2.
- Produces: Dispatcher que solo ejecuta tareas reclamadas y runtime que finaliza leases al guardar resultados.

- [ ] **Step 1: Write the failing test**

Actualizar la prueba de recuperación existente para expresar la nueva
garantía y añadir una competencia entre dos runtimes con la misma base:

```python
def test_two_runtimes_do_not_dispatch_the_same_recovered_task(tmp_path):
    database = tmp_path / "trama.db"
    first = TramaRuntime(state_store=SqliteStateStore(database), lease_seconds=30)
    first.register_project(scoped_manifest())
    first.submit_task(task("task-1"))
    assert first.wait_for_idle(timeout=2)

    second_coordination = RecordingCoordination()
    second = TramaRuntime(
        coordination=second_coordination,
        state_store=SqliteStateStore(database),
        lease_seconds=30,
    )
    try:
        assert second.wait_for_idle(timeout=2)
        assert second_coordination.seen == []
    finally:
        first.close()
        second.close()
```

Añadir una variante con lease expirado que compruebe que la segunda instancia
sí puede recuperar la tarea, y una prueba que registra un `AgentResult` y
comprueba que una entrega posterior no vuelve a despacharla. Mantener las
pruebas locales sin `state_store` sin cambios de comportamiento.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runtime.py -q`

Expected: FAIL en la prueba de dos runtimes porque ambos dispatchers todavía
encolan y ejecutan la tarea recuperada.

- [ ] **Step 3: Write minimal implementation**

Extender `TaskDispatcher` con un `TaskLeaseManager` opcional. En `_worker`,
después de comprobar que la tarea está en `accepted` o `running` y antes de
emitir `task.dispatch`, llamar a `manager.claim`; si devuelve `None`, liberar
la reserva y continuar. Registrar la renovación al iniciar el despacho,
liberar en error y exponer `complete_task_lease(task)` para el runtime.

`TramaRuntime` generará un `worker_id` UUID si no se proporciona, construirá
el manager cuando exista un `state_store`, dejará de convertir
automáticamente todo `running` a `accepted` y pasará `lease_seconds` al
dispatcher. `record_result` completará el lease por namespace después de
persistir el estado terminal. Añadir `task_lease_seconds` a `TramaSettings`
con el entorno `TRAMA_TASK_LEASE_SECONDS` y pasar el valor desde API/CLI sin
crear archivos de configuración.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_runtime.py tests/test_settings.py -q`

Expected: PASS, incluyendo no duplicación entre runtimes y recuperación tras
expiración.

- [ ] **Step 5: Commit**

```powershell
git add src/trama_platform/queueing.py src/trama_platform/runtime.py src/trama_platform/settings.py src/trama_platform/api.py tests/test_runtime.py tests/test_settings.py
git commit -m "feat: coordinar despacho mediante leases"
```

### Task 4: Conectar el worker distribuido y documentar operación

**Files:**
- Modify: `src/trama_platform/worker.py`
- Modify: `README.md`
- Modify: `docs/ARQUITECTURA.md`
- Test: `tests/test_worker.py`

**Interfaces:**
- Consumes: `task_lease_seconds` y `build_coordination` existentes.
- Produces: Worker distribuido que usa el coordinador configurado y documentación del ciclo lease/redelivery.

- [ ] **Step 1: Write the failing test**

Crear `tests/test_worker.py` con `TramaRuntime` y `build_coordination`
monkeypatcheados, y comprobar que `serve_task_worker` construye el runtime
con la coordinación solicitada en settings antes de iniciar el consumidor.

- [ ] **Step 2: Run test to verify it fails**

Run: `.venv/Scripts/python.exe -m pytest tests/test_worker.py -q`

Expected: FAIL porque el worker actual construye `TramaRuntime` sin pasar
`build_coordination(settings)`.

- [ ] **Step 3: Write minimal implementation**

Importar `build_coordination` en `worker.py` y pasar su resultado junto con
`lease_seconds=settings.task_lease_seconds`. Mantener los argumentos
inyectables de runtime, conexión y connect para las pruebas. Documentar que
un evento duplicado puede confirmarse sin ejecución si otro owner conserva el
lease, y que un worker caído se recupera al vencer `expires_at`.

- [ ] **Step 4: Run test to verify it passes**

Run: `.venv/Scripts/python.exe -m pytest tests/test_worker.py tests/test_nats_consumer.py -q`

Expected: PASS, incluyendo ack después del handler y la configuración de
redelivery existente.

- [ ] **Step 5: Commit**

```powershell
git add src/trama_platform/worker.py README.md docs/ARQUITECTURA.md tests/test_worker.py
git commit -m "feat: activar leases y coordinacion en el worker"
```

### Task 5: Verificación final y revisión de entrega

**Files:**
- Test: `tests/test_leases.py`
- Test: `tests/test_state_store_leases.py`
- Test: `tests/test_runtime.py`
- Test: `tests/test_worker.py`

- [ ] **Step 1: Run the complete Python suite**

Run: `.venv/Scripts/python.exe -m pytest -q`

Expected: PASS con cero fallos; la advertencia deprecada existente de
Starlette no se interpreta como fallo.

- [ ] **Step 2: Run static and Go verification**

Run: `.venv/Scripts/python.exe -m ruff check .`

Run: `C:\Program Files\Go\bin\go.exe test ./...` desde `gateway`.

Run: `docker compose -f deploy/docker-compose.gateway.yml config --quiet`.

Expected: todos los comandos terminan con código 0.

- [ ] **Step 3: Inspect the final diff**

Run: `git diff origin/main...HEAD --check`

Run: `git diff origin/main...HEAD --name-only | Select-String -Pattern '(^|/)(settings\.json|\.env($|\.)|\.vscode(/|$))'`

Expected: sin errores de whitespace y sin archivos de configuración local o
secretos.

- [ ] **Step 4: Request code review**

Comparar `origin/main` contra `HEAD`, revisar especialmente la atomicidad del
claim, los filtros de namespace y la carrera entre renovación y expiración.
Resolver cualquier hallazgo crítico o importante antes de publicar la rama.

- [ ] **Step 5: Commit final de documentación si fuera necesario**

Solo si la verificación modifica documentación, usar un commit explícito:

```powershell
git add README.md docs/ARQUITECTURA.md
git commit -m "docs: documentar ownership y recuperacion de tareas"
```
