# Observabilidad y planificación Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persistir y visualizar el recorrido completo requisito → plan de IA master → aprobación → fases paralelas → tareas CCCC → logs y resultados.

**Architecture:** La API/runtime de TRAMA sigue siendo la fuente de verdad. Los eventos de transición permanecen en `OperationEvent`; los mensajes de ejecución se almacenan como `TaskLog`, ambos unidos por `correlation_id`. Hermes registra y presenta propuestas mediante MCP, CCCC ejecuta solo tareas aprobadas y la TUI consume proyecciones de observabilidad sin reconstruir el grafo por su cuenta.

**Tech Stack:** Python 3.12, Pydantic v2, SQLite, FastAPI/Starlette, httpx, MCP stdio, Textual, pytest y Ruff.

**Spec:** `docs/superpowers/specs/2026-09-15-observabilidad-planificacion-design.md`

## Global Constraints

- La API local continúa ligada a `127.0.0.1` y es la única fuente de estado operativo.
- La IA master puede proponer y explicar, pero nunca aprobar ni ejecutar tareas.
- Hermes conserva aprobaciones manuales y no activa YOLO ni automatizaciones desatendidas.
- CCCC recibe solo tareas aprobadas y mantiene asignación, handoffs y ejecución.
- Semantica y Utopia siguen siendo adaptadores opcionales; su fallo no invalida evidencia local.
- Cada dato operativo conserva `organization_id` y `project_id`; no se permiten cruces por defecto.
- Los logs se redactan antes de persistirse y tienen límites de longitud, metadata y retención.
- Los contratos y endpoints nuevos son aditivos y mantienen `schema_version = "1.0"`.
- Cada tarea termina con pruebas específicas y un commit pequeño y revisable.

## File Map

- Modify `src/trama_platform/contracts.py`: contratos `PlanProposal`, `TaskLog`, `TimelineEntry` y linaje opcional en `OperationEvent`.
- Create `src/trama_platform/observability.py`: redacción, límites y construcción de entradas de timeline.
- Modify `src/trama_platform/state_store.py`: tabla y consultas de logs; persistencia de propuestas.
- Modify `src/trama_platform/runtime.py`: correlación, propuestas, timelines y proyección del radar.
- Modify `src/trama_platform/api.py`: consultas de logs/timelines y planes.
- Modify `src/trama_platform/mcp_server.py`, `src/trama_platform/hermes.py` y `src/trama_platform/ports.py`: interfaz supervisada de Hermes y tipos de puerto.
- Modify `src/trama_platform/tui.py`: radar de fases, cola, actividad reciente y detalle de tarea.
- Modify `README.md`, `docs/ARQUITECTURA.md` y `AGENTS.md`: flujo y comandos observables.
- Create or modify tests in `tests/test_observability.py`, `test_state_store.py`, `test_runtime.py`, `test_api.py`, `test_mcp.py` and `test_tui.py`.

---

### Task 1: Contratos y redacción segura

**Files:**
- Modify: `src/trama_platform/contracts.py`
- Create: `src/trama_platform/observability.py`
- Test: `tests/test_observability.py`

**Interfaces:**
- Produces `PlanProposal`, `TaskLog`, `TimelineEntry`, `LogLevel` and `PlanProposalStatus`.
- Produces `sanitize_message(message: str, metadata: Mapping[str, Any]) -> tuple[str, dict[str, Any]]`.
- `TaskLog` accepts `log_id`, `created_at`, `level`, `message`, lineage IDs, `actor`, `correlation_id`, optional `duration_ms`, `sequence` and bounded `metadata`.

- [ ] **Step 1: Write failing contract and redaction tests.**

```python
def test_task_log_redacts_tokens_and_bounds_metadata():
    from trama_platform.observability import sanitize_message
    message, metadata = sanitize_message(
        "Authorization: Bearer super-secret",
        {"token": "super-secret", "ok": "visible"},
    )
    assert "super-secret" not in message
    assert metadata["token"] == "[REDACTED]"
    assert metadata["ok"] == "visible"
```

- [ ] **Step 2: Run the focused test and verify it fails.**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_observability.py -q`
Expected: FAIL because the new models and sanitizer do not exist.

- [ ] **Step 3: Implement the models and sanitizer.**

Add `schema_version = "1.0"`, strict Pydantic bounds, optional lineage fields on `OperationEvent`, and redact case-insensitive keys matching `token`, `secret`, `password`, `cookie`, `authorization`, `api_key`, plus values that look like bearer tokens or private keys. Keep the original object immutable and return a sanitized copy.

- [ ] **Step 4: Run contract tests and lint.**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_observability.py -q` and `.\.venv\Scripts\python.exe -m ruff check src/trama_platform/contracts.py src/trama_platform/observability.py tests/test_observability.py`
Expected: PASS and `All checks passed!`.

- [ ] **Step 5: Commit.**

```powershell
git add src/trama_platform/contracts.py src/trama_platform/observability.py tests/test_observability.py
git commit -m "feat: add observability contracts and redaction"
```

### Task 2: Persistencia SQLite de propuestas y logs

**Files:**
- Modify: `src/trama_platform/state_store.py`
- Test: `tests/test_state_store.py`

**Interfaces:**
- `SqliteStateStore.save_plan_proposal(proposal: PlanProposal) -> None` and `load_plan_proposals() -> list[PlanProposal]` use `state_records` kind `plan_proposal`.
- `append_task_log(log: TaskLog) -> None` persists a log atomically.
- `list_task_logs(*, organization_id: str | None = None, project_id: str | None = None, task_id: str | None = None, phase_id: str | None = None, requirement_id: str | None = None, level: LogLevel | None = None, limit: int = 100) -> list[TaskLog]` returns ascending sequence/time order.
- `count_task_logs(...) -> int` and `prune_task_logs(organization_id: str, project_id: str, max_rows: int) -> int` expose retention metrics.

- [ ] **Step 1: Add failing round-trip, filter and retention tests.**

Cover restart round-trip for a `PlanProposal`, ordering by `(created_at, sequence)`, filters that never cross `project_id`, and pruning that keeps the newest rows while returning the number deleted.

- [ ] **Step 2: Run the focused tests and verify failure.**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_state_store.py -k "proposal or log or retention" -q`
Expected: FAIL with missing store methods/table.

- [ ] **Step 3: Implement the durable log table and methods.**

Create `task_logs` with indexes on `project_id`, `task_id`, `phase_id`, `requirement_id`, `created_at`; serialize through Pydantic JSON; call `sanitize_message` at the store boundary as defense in depth. Keep `operation_events` unchanged except for the additive payload fields.

- [ ] **Step 4: Verify persistence and existing state-store tests.**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_state_store.py -q`
Expected: all state-store tests PASS.

- [ ] **Step 5: Commit.**

```powershell
git add src/trama_platform/state_store.py tests/test_state_store.py
git commit -m "feat: persist task logs and plan proposals"
```

### Task 3: Runtime correlation, plan approval and timelines

**Files:**
- Modify: `src/trama_platform/runtime.py`
- Modify: `src/trama_platform/ports.py`
- Test: `tests/test_runtime.py`

**Interfaces:**
- `register_plan_proposal(proposal: PlanProposal) -> PlanProposal` validates organization/project/requirement lineage and records `plan.proposed`.
- `approve_plan(proposal_id: str, approver: str) -> PlanProposal` records `plan.approve`, approves its phases/tasks without bypassing dependencies, and never dispatches a task directly.
- `record_task_log(log: TaskLog) -> TaskLog` sanitizes, persists and returns the log.
- `task_timeline(task_id: str, limit: int = 100) -> list[TimelineEntry]` and `phase_timeline(phase_id: str, limit: int = 100) -> list[TimelineEntry]` merge events/logs in stable order.
- `overview()` adds `parallel_groups`, `pending_approval`, `blocked_dependencies` and `latest_activity`.

- [ ] **Step 1: Add failing runtime tests.**

Test that two approved phases without dependencies appear in separate parallel groups, a dependent phase remains planned, plan approval emits an auditable event, a task log shares the task correlation ID, and `task_timeline` returns event/log/event order.

- [ ] **Step 2: Run runtime tests to confirm failure.**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_runtime.py -k "plan or timeline or parallel or log" -q`
Expected: FAIL with missing methods and overview keys.

- [ ] **Step 3: Implement the runtime methods and correlation propagation.**

Generate one `correlation_id` per proposal and inherit it into derived phases/tasks. Extend `_record_event` and task transition paths to include lineage. Persist a `TaskLog` for dispatch start, CCCC handoff, retries, result and dependency blocking. Reuse `_refresh_planning_state` so parallel readiness remains deterministic.

- [ ] **Step 4: Run targeted and full runtime tests.**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_runtime.py -q` and then `.\.venv\Scripts\python.exe -m pytest -q`
Expected: targeted and full suites PASS.

- [ ] **Step 5: Commit.**

```powershell
git add src/trama_platform/runtime.py src/trama_platform/ports.py tests/test_runtime.py
git commit -m "feat: correlate runtime timelines and parallel plans"
```

### Task 4: API, MCP y frontera de Hermes

**Files:**
- Modify: `src/trama_platform/api.py`
- Modify: `src/trama_platform/mcp_server.py`
- Modify: `src/trama_platform/hermes.py`
- Test: `tests/test_api.py`, `tests/test_mcp.py`, `tests/test_hermes.py`

**Interfaces:**
- API: `GET /v1/tasks/{task_id}/timeline`, `GET /v1/phases/{phase_id}/timeline`, `GET /v1/logs`, `GET /v1/plans/{proposal_id}`.
- API responses are JSON arrays/models and accept `limit` bounded to `1..1000` plus lineage filters.
- MCP client methods: `get_task_timeline`, `get_phase_timeline`, `list_logs`, `get_plan`, `register_plan_proposal` and `approve_plan`.
- Hermes `TRAMA_TOOLS` includes only these supervised operations; no tool performs approval implicitly.

- [ ] **Step 1: Write failing API/MCP/config tests.**

Assert endpoint filtering, 404 for unknown task/phase/plan, organization/project isolation, MCP forwarding to exact paths, and Hermes configuration containing the new tool names without YOLO.

- [ ] **Step 2: Run focused tests to verify failure.**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_mcp.py tests/test_hermes.py -k "timeline or logs or plan" -q`
Expected: FAIL because routes and client methods are absent.

- [ ] **Step 3: Implement routes and MCP forwarding.**

Use the existing bearer-token middleware and add explicit `organization_id`/`project_id` query filters where the current API does not infer tenant context. Enforce those filters in runtime before returning any log, proposal or timeline, convert `KeyError` to HTTP 404, preserve `limit` bounds, and keep MCP stateless by forwarding every operation to the API.

- [ ] **Step 4: Run API/MCP tests and lint.**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_mcp.py tests/test_hermes.py -q` and Ruff on touched files.
Expected: PASS and no new lint errors.

- [ ] **Step 5: Commit.**

```powershell
git add src/trama_platform/api.py src/trama_platform/mcp_server.py src/trama_platform/hermes.py tests/test_api.py tests/test_mcp.py tests/test_hermes.py
git commit -m "feat: expose observability through api and mcp"
```

### Task 5: TUI radar de observabilidad

**Files:**
- Modify: `src/trama_platform/tui.py`
- Test: `tests/test_tui.py`

**Interfaces:**
- The existing `TramaTuiApp` keeps `r` and `q`; add `Enter`/`Esc` actions and a selected task ID.
- Consume `overview.parallel_groups`, `overview.pending_approval`, `overview.blocked_dependencies`, `overview.latest_activity` and `get_task_timeline` when available.
- Keep a fallback rendering path for fake/legacy clients that only expose status, tasks and agents.

- [ ] **Step 1: Add failing Textual tests.**

Cover compact parallel lanes, an approval queue distinct from CCCC, latest activity, selecting a queue row with `Enter`, rendering timeline entries, returning with `Esc`, and the approved dark-blue/purple/orange palette.

- [ ] **Step 2: Run TUI tests to verify failure.**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_tui.py -q`
Expected: FAIL for missing panels/actions and timeline calls.

- [ ] **Step 3: Implement the radar layout.**

Keep dense panels and short labels. Use one phase lane per parallel group, show arrows/attenuation for dependencies, group queue rows by phase, add an activity panel and a detail panel backed by the API timeline. Preserve the current orange/blue-night/purple CSS and avoid oversized percentage widgets.

- [ ] **Step 4: Verify rendering and keyboard flow.**

Run: `.\.venv\Scripts\python.exe -m pytest tests/test_tui.py -q` and launch `.\.venv\Scripts\python.exe -m trama_platform tui` manually for `r`, `Enter`, `Esc` and `q`.
Expected: tests PASS and the interactive window shows phases, queues and timeline without traceback.

- [ ] **Step 5: Commit.**

```powershell
git add src/trama_platform/tui.py tests/test_tui.py
git commit -m "feat: add tui observability radar"
```

### Task 6: Documentación, integración y verificación final

**Files:**
- Modify: `README.md`, `docs/ARQUITECTURA.md`, `AGENTS.md`
- Test: full repository test/lint commands

- [ ] **Step 1: Document commands and data flow.**

Add examples for querying timelines and logs, explain the master planner approval boundary, and document retention/redaction settings without adding credentials or changing the local bind policy.

- [ ] **Step 2: Run the complete verification set.**

Run: `.\.venv\Scripts\python.exe -m pytest -q`, `.\.venv\Scripts\python.exe -m ruff check src tests`, and `git diff --check`.
Expected: tests PASS; any pre-existing lint issue must be reported separately rather than hidden.

- [ ] **Step 3: Inspect the final diff and state.**

Run: `git diff --stat`, `git diff -- docs/ README.md AGENTS.md`, and `git status --short`; verify no secrets, generated databases or unrelated user changes were staged.

- [ ] **Step 4: Commit documentation only.**

```powershell
git add README.md docs/ARQUITECTURA.md AGENTS.md
git commit -m "docs: document observability workflow"
```
