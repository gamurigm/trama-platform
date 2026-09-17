# Runtime aislado por namespace Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evitar que identificadores iguales de organizaciones distintas colisionen en los registros en memoria, la coordinación, el runtime y los endpoints con IDs.

**Architecture:** Se añade `ScopedStore`, una colección interna indexada por `(organization_id, entity_id)` con compatibilidad para el namespace `default`. El runtime propagará la organización al resolver IDs y `AgentResult` transportará el namespace del resultado; las URLs HTTP no cambian.

**Tech Stack:** Python 3.12, dataclasses, Pydantic 2, FastAPI, pytest y Ruff.

**Spec:** `docs/superpowers/specs/2026-09-17-namespace-isolated-runtime-design.md`

## Global Constraints

- La clave interna de cada entidad será `(organization_id, entity_id)`.
- La ausencia de organización solo conserva compatibilidad cuando no existe ambigüedad.
- Las URLs públicas permanecen sin cambios; el tenant se obtiene de `RequestContext`.
- No se crean ni versionan `settings.json`, `.env`, `.vscode`, credenciales ni tokens.
- Se mantienen los contratos versionados `1.0` con campos nuevos compatibles por defecto.
- Las dependencias de tareas, fases y propuestas se resuelven dentro de la organización y proyecto correctos.

---

### Task 1: Colección namespace-aware y contratos de coordinación

**Files:**
- Modify: `src/trama_platform/namespaces.py`
- Modify: `src/trama_platform/contracts.py`
- Modify: `src/trama_platform/ports.py`
- Modify: `src/trama_platform/runtime.py`
- Test: `tests/test_namespaces.py`
- Test: `tests/test_runtime.py`

**Interfaces:**
- Produce: `NamespaceKey`, `namespace_key()`, `ScopedStore` y `AgentResult.organization_id`.
- Consumers: runtime, coordinación, stores y API.

- [x] **Step 1: Write the failing tests**

Añadir pruebas que registren dos valores con el mismo ID en organizaciones
distintas, que `ScopedStore.find` los separe y que una búsqueda sin
organización rechace la ambigüedad. Añadir una prueba de runtime que registre
dos proyectos y dos tareas iguales pero con distinto namespace.

- [x] **Step 2: Run the focused tests and verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_namespaces.py tests/test_runtime.py -q`

Expected: FAIL porque no existe `ScopedStore` y los registros actuales
sobrescriben la primera entidad.

- [x] **Step 3: Implement the minimal scoped collection**

Implementar `ScopedStore` con almacenamiento interno por tupla, `find`,
`get`, `update`, `values`, `items`, `__getitem__`, `__setitem__`,
`__contains__` y `__len__`. La lectura de string simple mapeará al namespace
`default`; `find(id, organization_id=None)` levantará `ValueError` si hay más
de una coincidencia.

Cambiar `AgentResult` para incluir:

```python
organization_id: str = Field(default="default", min_length=1, max_length=100)
```

Convertir las colecciones de runtime y coordinación a `ScopedStore` y usar la
clave del objeto al insertar o actualizar.

- [x] **Step 4: Run focused tests and existing runtime tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_namespaces.py tests/test_runtime.py tests/test_state_store.py -q`

Expected: PASS, incluyendo las llamadas históricas del namespace `default`.

- [x] **Step 5: Commit**

```powershell
git add src/trama_platform/namespaces.py src/trama_platform/contracts.py src/trama_platform/ports.py src/trama_platform/runtime.py tests/test_namespaces.py tests/test_runtime.py tests/test_state_store.py
git commit -m "feat: aislar registros en memoria por organizacion"
```

### Task 2: Propagación de namespace en runtime, dispatcher y persistencia

**Files:**
- Modify: `src/trama_platform/queueing.py`
- Modify: `src/trama_platform/runtime.py`
- Modify: `src/trama_platform/state_store.py`
- Modify: `src/trama_platform/adapters.py`
- Modify: `src/trama_platform/mcp_server.py`
- Test: `tests/test_queueing.py`
- Test: `tests/test_state_store.py`
- Test: `tests/test_state_store_leases.py`

**Interfaces:**
- Consumes: `ScopedStore` y `AgentResult.organization_id`.
- Produces: lookups internos con organización explícita y resultados persistidos
  en el namespace del task.

- [x] **Step 1: Write the failing tests**

Añadir una prueba de dispatcher donde dos tareas del mismo `task_id` pero de
organizaciones distintas se recuperen y cada coordinación reciba únicamente
la tarea de su namespace. Añadir una prueba de resultado donde dos runtimes
registren el mismo ID en distintas organizaciones sin sobrescribirse.

- [x] **Step 2: Run tests and verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_queueing.py tests/test_state_store.py tests/test_state_store_leases.py -q`

Expected: FAIL porque `TaskLookup` recibe solo `task_id` y el runtime comparte
el mismo índice para ambas organizaciones.

- [x] **Step 3: Implement namespace propagation**

Cambiar `TaskLookup` para recibir `(organization_id, task_id)`, actualizar el
dispatcher y resolver dependencias con la organización del task. Hacer que
`get_task`, `get_result`, `get_project`, `get_requirement`, `get_plan_proposal`,
timelines y operaciones de lifecycle acepten el namespace opcional.

Actualizar `save_task_result`/`save_result` para persistir el
`organization_id` del resultado en PostgreSQL y mantener la validación del
intento del lease. Mantener el adaptador CCCC compatible con productores
anteriores mediante el valor `default`.

- [x] **Step 4: Run focused tests**

Run: `.venv/Scripts/python.exe -m pytest tests/test_queueing.py tests/test_state_store.py tests/test_state_store_leases.py tests/test_runtime.py -q`

Expected: PASS sin colisiones entre namespaces.

- [x] **Step 5: Commit**

```powershell
git add src/trama_platform/queueing.py src/trama_platform/runtime.py src/trama_platform/state_store.py src/trama_platform/adapters.py src/trama_platform/mcp_server.py tests/test_queueing.py tests/test_state_store.py tests/test_state_store_leases.py
git commit -m "feat: propagar namespace en despacho y resultados"
```

### Task 3: Aislamiento de endpoints y regresión final

**Files:**
- Modify: `src/trama_platform/api.py`
- Modify: `src/trama_platform/mcp_server.py`
- Modify: `src/trama_platform/runtime.py`
- Modify: `README.md`
- Modify: `docs/ARQUITECTURA.md`
- Test: `tests/test_api.py`
- Test: `tests/test_mcp_server.py`

**Interfaces:**
- Consumes: métodos del runtime con `organization_id` opcional.
- Produces: endpoints tenant-aware que no seleccionan otro registro antes de
  ejecutar `ensure_namespace`.

- [x] **Step 1: Write failing API tests**

Probar dos organizaciones con el mismo `task_id`: cada header
`X-Organization-ID` obtiene su tarea, y un resultado, cancelación, reintento,
aprobación o timeline no puede operar sobre el task de otra organización.

- [x] **Step 2: Run API tests and verify failure**

Run: `.venv/Scripts/python.exe -m pytest tests/test_api.py tests/test_mcp_server.py -q`

Expected: FAIL porque los endpoints resuelven sus IDs sin pasar el contexto.

- [x] **Step 3: Implement context propagation**

Extraer la organización de `RequestContext`, pasarla a los métodos de lookup
y convertir la ambigüedad en HTTP 409 o 404 según corresponda. Al registrar
resultados, completar el namespace compatible solo cuando el tenant del request
esté autorizado. Mantener las URLs y las respuestas exitosas existentes.

Documentar el contrato en README y arquitectura: IDs no son globales, el
namespace es obligatorio en producción y los lookups ambiguos se rechazan.

- [x] **Step 4: Run the complete verification**

Run:

```powershell
.venv/Scripts/python.exe -m pytest -q
.venv/Scripts/python.exe -m ruff check .
git diff origin/main...HEAD --check
git diff origin/main...HEAD --name-only | Select-String -Pattern '(^|/)(settings\.json|\.env($|\.)|\.vscode(/|$))'
```

Expected: all tests and Ruff pass; no whitespace errors or forbidden local
configuration files appear.

- [x] **Step 5: Commit**

```powershell
git add src/trama_platform/api.py src/trama_platform/mcp_server.py src/trama_platform/runtime.py README.md docs/ARQUITECTURA.md tests/test_api.py tests/test_mcp_server.py
git commit -m "fix: reforzar aislamiento tenant en la api"
```
