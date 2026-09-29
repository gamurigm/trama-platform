# TRAMA Full TypeScript TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use `superpowers:executing-plans` to implement this plan task-by-task.

**Goal:** Make OpenTUI the only TRAMA TUI, able to operate the control plane and configure/inspect supported integrations.

**Architecture:** Bun/OpenTUI owns all terminal screens and uses a typed client for the existing Python FastAPI service. Python remains the source of business state and adapters; it adds per-user settings, credential storage, missing read/mutation endpoints, integration diagnostics, and a thin launcher for the TypeScript application.

**Tech Stack:** TypeScript, Bun, OpenTUI, Python 3.12+, FastAPI, Pydantic, `keyring` Windows backend, Windows Credential Manager.

**Spec:** `docs/superpowers/specs/2026-09-27-trama-typescript-tui-design.md`

## Global Constraints

- Python requires `>=3.12,<3.15`.
- The local API remains bound to `127.0.0.1` by default.
- Non-secret per-user settings live under `%LOCALAPPDATA%\TRAMA\`, outside the repository.
- Secrets are stored in Windows Credential Manager; never return, log, or display their values.
- Environment variables override saved per-user settings, and the UI identifies the active source.
- Preserve the existing repo-local `artifacts/state/trama.db` when the global launcher is used from another working directory.
- Plan/task approvals remain explicit human actions; the feature does not install Hermes or other external tools.
- Keep Python as API/control plane/CLI; implement every TUI screen and interaction in TypeScript.
- Preserve existing user changes in `AGENTS.md`, `src/trama_platform/runtime.py`, `tests/test_runtime.py`, and unrelated untracked paths.
- Do not add or run automated tests as part of this plan; validate through type/build checks and the specified manual flows.

## Review Focus

1. Environment override hides a saved value: the Integrations screen must show the active source and pending-restart state. Manual check in Task 6.
2. A saved URL/token is unreachable or a binary is missing: display the actual health state, never “connected”. Manual check in Task 6.
3. A secret is set, replaced, cleared, or rejected by the OS vault: no response, exception, UI output, or log may contain it. Manual check in Task 1 and Task 6.
4. Hermes configuration already has unrelated settings: write only the TRAMA MCP entry and preserve the rest. Manual check in Task 2.
5. A plan/task is pending approval or the CCCC daemon is stopped: do not dispatch or report activity as running without the explicit action. Manual check in Task 5 and Task 6.

## Implementation Tasks

### Task 1: Per-user settings and Windows credential vault

**Files:**
- Create: `src/trama_platform/user_config.py`
- Create: `src/trama_platform/credential_store.py`
- Modify: `src/trama_platform/settings.py`
- Modify: `pyproject.toml`
- Modify: `uv.lock`

**Interfaces:**
- `UserConfigStore.read() -> dict[str, object]`
- `UserConfigStore.update(values: dict[str, object]) -> dict[str, object]`
- `CredentialStore.has(name: str) -> bool`
- `CredentialStore.set(name: str, value: str) -> None`
- `CredentialStore.get(name: str) -> str | None`
- `CredentialStore.delete(name: str) -> None`
- `TramaSettings.from_env()` keeps its public signature and resolves environment values over saved user settings.
- `TramaSettings.state_path` resolves relative paths under `TRAMA_APP_ROOT` when the global launcher sets it, otherwise preserving current working-directory behavior.

- [ ] Add `keyring>=25.7,<26` (the current stable Windows backend is documented by [keyring](https://github.com/jaraco/keyring/blob/main/keyring/backends/Windows.py)) and update `uv.lock`; require the Windows Credential Manager backend for secrets and fail closed if the secure backend is unavailable.
- [ ] Implement validated, allowlisted non-secret settings at `%LOCALAPPDATA%\TRAMA\config.json`; create the directory only when saving and never put secret keys/values in this file.
- [ ] Implement named credential operations under a TRAMA-specific service name. `has` and `set`/`get`/`delete` must not log or include secret values in errors.
- [ ] Resolve built-in defaults, saved settings, vault secrets, then environment overrides; expose the active source separately from values.
- [ ] Resolve relative state paths against `TRAMA_APP_ROOT` when present so global `trama up/down` continue using the existing repo database from any caller directory; do not move or migrate the current database.
- [ ] Run `.\.venv\Scripts\python.exe -m compileall -q src/trama_platform`; inspect the config file shape to confirm it contains no credential fields.

### Task 2: Configuration, planning-list, and integration API

**Files:**
- Create: `src/trama_platform/config_contracts.py`
- Create: `src/trama_platform/integration_status.py`
- Modify: `src/trama_platform/api.py`
- Modify: `src/trama_platform/runtime.py` (preserve the existing uncommitted task-refresh changes)
- Modify: `src/trama_platform/state_store.py`
- Modify: `src/trama_platform/hermes.py`

**Interfaces:**
- `GET /v1/config` returns non-secret settings, setting sources, and `restart_required`; it never returns credential values.
- `PUT /v1/config` validates and saves allowlisted non-secret settings.
- `GET /v1/config/secrets` returns configured names only.
- `PUT /v1/config/secrets/{name}` accepts `{ "value": string }`, stores it, and returns `{ "configured": true }`.
- `DELETE /v1/config/secrets/{name}` deletes it and returns `{ "configured": false }`.
- `GET /v1/integrations` returns `IntegrationReport[]` and the server MCP tool inventory.
- `POST /v1/integrations/{integration_id}/check` returns one fresh `IntegrationReport`.
- `GET /v1/plans` returns saved plan proposals in creation order.
- `IntegrationReport` fields: `id`, `label`, `status`, `configured`, `detail`, `checked_at`, and `tools` (empty except for MCP).
- The config response reports only whether the API token is configured. The Python launcher passes the effective API token to the child process through its environment so the TypeScript client can authorize requests without a secret-return API.

- [ ] Add `list_plan_proposals()` to the state store/runtime and expose `GET /v1/plans` without changing plan persistence contracts.
- [ ] Add the config contracts and routes above; reject unknown settings and keep secrets out of all read responses.
- [ ] Build integration checks with bounded timeouts and argument arrays (`shell=False`): CCCC executable/daemon, Hermes executable/config/MCP entry, Semantica path/package, Utopia endpoint, Colibri endpoint, gateway health, and NATS reachability when configured.
- [ ] Return explicit states: `connected`, `unreachable`, `not_configured`, `not_installed`, `stopped`, or `not_implemented`. Keep model gateway marked `not_implemented` until a model adapter exists.
- [ ] Add explicit CCCC daemon start/stop endpoints using the configured executable, with no shell invocation and no automatic starts.
- [ ] Update Hermes config writing to merge only `mcp_servers.trama`, preserve other YAML keys, use the absolute repository path for the MCP command, and retain manual-approval settings.
- [ ] Compile the Python package; inspect representative config/integration responses to verify the response schemas contain no secret fields.

### Task 3: Typed TypeScript API client

**Files:**
- Modify: `tui/src/api/types.ts`
- Modify: `tui/src/api/client.ts`

**Interfaces:**
- Add types for `Project`, `Requirement`, `Phase`, `PlanProposal`, `TaskEnvelope`, `TaskLog`, `TimelineEntry`, `ConfigSnapshot`, and `IntegrationReport`.
- Add client methods for project list/get/register; requirement and phase list/register; plan list/register/approve; task list/get/submit/approve/cancel/retry; logs/timelines/agents; config read/update; secret set/delete/list; integration list/check; and CCCC daemon control.
- Keep the existing constructor `new TramaApiClient(baseUrl, fetchImpl?, timeoutMs?)`.
- Keep the HTTP client limited to HTTP requests; place process orchestration in `tui/src/lifecycle.ts` as `restartManagedApi(pythonExecutable: string, appRoot: string): Promise<void>`.

- [ ] Add strict payload validators for each response and request; preserve current timeout and `ApiError` behavior.
- [ ] Implement the methods against the existing route shapes and the new Task 2 routes.
- [ ] Keep secret writes as request-only payloads: the returned client type contains only secret name/configured state. Add an optional in-memory API token and apply it as a Bearer header without logging it; update this value in memory when the operator saves a new API token.
- [ ] Run the TypeScript compiler with `bun run --cwd tui tsc --noEmit -p tsconfig.json`.

### Task 4: TypeScript navigation and project/planning workflows

**Files:**
- Modify: `tui/src/App.tsx`
- Create: `tui/src/components/Navigation.tsx`
- Create: `tui/src/components/ProjectsView.tsx`
- Create: `tui/src/components/PlanningView.tsx`
- Create: `tui/src/components/FormFields.tsx`

**Interfaces:**
- `App` owns the selected view, selected project, loading/error state, and refresh action.
- `Navigation` receives `activeView` and `onSelect(view)` and shows keyboard help.
- `ProjectsView` receives the API client and provides list/inspect/register flows.
- `PlanningView` receives the API client and selected project and provides requirement/phase/plan flows.
- A shared `tui/src/theme.ts` exports the palette and status styles; shared panel and status components keep the visual system consistent.

- [ ] Replace the single dashboard render with keyboard-first navigation for Overview, Projects, Planning, Tasks, Activity, and Integrations.
- [ ] Define a deep navy base, violet/cyan accents, amber approval states, coral blocked/error states, and high-contrast text in `theme.ts`; use shared compact panels, clear selection/focus styling, progress indicators, and polished loading/empty/error states across every view.
- [ ] Use available terminal width to reflow panels and tables; at narrow widths prioritize names, status, and primary actions, moving secondary details into inspect screens rather than clipping content.
- [ ] Add labeled project fields for ID, repository, branch, capabilities, and commands; validate required values before submitting.
- [ ] Add requirement and phase forms with acceptance criteria and dependencies; make parallel phases explicit when they have no dependencies.
- [ ] Add proposal creation/list/detail and a confirmation step before plan or phase approval; show approver and resulting state.
- [ ] Preserve dashboard overview, responsive narrow-terminal layout, polling, refresh, and quit behavior.
- [ ] Run `bun run --cwd tui tsc --noEmit -p tsconfig.json` and manually register a project, requirement, phase, and plan through the TUI.

### Task 5: TypeScript task queue and observability workflows

**Files:**
- Modify: `tui/src/components/TaskTable.tsx`
- Create: `tui/src/components/TasksView.tsx`
- Create: `tui/src/components/ObservabilityView.tsx`
- Modify: `tui/src/App.tsx`

**Interfaces:**
- `TasksView` receives the API client and selected project; it lists, submits, inspects, approves, cancels, and retries tasks.
- `ObservabilityView` receives the API client and filters for project/requirement/phase/task/level.

- [ ] Add task submit form fields matching `TaskEnvelope`: objective, actor, repository, branch, worktree, allowed paths, dependencies, and acceptance criteria.
- [ ] Keep planned tasks in the approval queue; require explicit confirmation for approve/cancel/retry operations.
- [ ] Add task detail with timeline and phase detail with timeline; show latest sanitized logs and their correlation IDs.
- [ ] Display queue, blocked, and running state from API responses rather than inferring it from form actions.
- [ ] Run `bun run --cwd tui tsc --noEmit -p tsconfig.json` and manually submit a task, inspect its timeline/logs, and confirm pending approval does not dispatch it.

### Task 6: Integrations and configuration workflows

**Files:**
- Create: `tui/src/components/IntegrationsView.tsx`
- Modify: `tui/src/api/types.ts`
- Modify: `tui/src/api/client.ts`
- Modify: `tui/src/App.tsx`

**Interfaces:**
- `IntegrationsView` displays `IntegrationReport[]`, `ConfigSnapshot`, and the MCP tool inventory.
- Config forms call the Task 3 API methods; secret inputs are masked and never prefilled.
- Listener host, API port, and state directory are visible with source labels but read-only; this keeps the local API address and existing database path stable while it restarts.
- `tui/src/lifecycle.ts` exports `restartManagedApi(pythonExecutable: string, appRoot: string): Promise<void>`; it runs the provided Python executable with `-m trama_platform down`, waits for success, then runs `-m trama_platform up`, inherits `TRAMA_APP_ROOT`, and never uses a shell.

- [ ] Group settings by General, CCCC, Hermes/MCP, Semantica, Utopia, Colibri, Gateway, and NATS; show source (`default`, `environment`, or `user`) and restart-required state.
- [ ] Add save/test/clear controls; show connection results without secret material; after a successful save, offer explicit API restart through `lifecycle.ts` when required.
- [ ] Show Hermes as `not_installed` on this machine; allow preparing/merging its MCP entry without installing Hermes.
- [ ] Show CCCC version/daemon/backend state; start/stop only through explicit actions and show that TRAMA remains in memory mode until configuration is applied.
- [ ] Distinguish server-advertised MCP tools from the Hermes-configured allowlist.
- [ ] Run `bun run --cwd tui tsc --noEmit -p tsconfig.json` and manually verify missing Hermes, stopped CCCC, environment overrides, a configured-but-unreachable service, and secret replacement/clearing without secret output.

### Task 7: Make TypeScript the only TUI and update launchers/docs

**Files:**
- Modify: `src/trama_platform/cli.py`
- Delete: `src/trama_platform/tui.py`
- Modify: `pyproject.toml` (remove `textual`)
- Delete: `tests/test_tui.py`
- Modify: `README.md`
- Modify: `C:\Users\gamur\.local\bin\trama.cmd`
- Modify: `uv.lock`

**Interfaces:**
- `trama tui` delegates to `bun run --cwd tui start` from the repository root and returns Bun's exit status.
- Bare global `trama` starts the managed API if needed, then invokes `trama tui`; all supplied CLI arguments continue forwarding to the Python CLI.

- [ ] Resolve the repository/TUI path without relying on the caller's current directory; launch Bun without shell interpolation.
- [ ] Update the global shim to set `TRAMA_APP_ROOT` to the project root, preserve the caller's working directory and CLI argument forwarding, start the API before the bare-command TUI, and surface startup errors.
- [ ] Have the Python CLI pass `TRAMA_PYTHON_EXECUTABLE=sys.executable` and the effective API token as `TRAMA_UI_API_TOKEN` to Bun; keep `TRAMA_UI_API_TOKEN` distinct from `TRAMA_API_TOKEN` so it never overrides saved configuration during restart.
- [ ] Remove the Textual import/dispatch branch and its source, dedicated test file, and runtime dependency.
- [ ] Update README launch instructions, screens, keyboard controls, connector status meanings, and Hermes missing/setup behavior.
- [ ] From a fresh PowerShell outside the repository, manually verify `trama`, `trama tui`, `trama status`, and `trama down`; confirm all use the existing repo-local database and do not create `artifacts` in the caller's directory.

### Task 8: Final acceptance walkthrough

**Files:** no additional files; resolve defects in the task that owns them.

- [x] Run `bun run --cwd tui tsc --noEmit -p tsconfig.json` and `.\.venv\Scripts\python.exe -m compileall -q src/trama_platform`.
- [x] Walk the approved flows in the live TUI: register a project; create a requirement, phases, and proposal; approve explicitly; submit/approve/cancel/retry a task; inspect timelines/logs; configure and test integrations.
- [x] Confirm unavailable Hermes and stopped CCCC are shown accurately, settings changes show source/restart state, and no credential value appears in files, terminal output, API responses, or logs.
- [x] Review every view at wide and narrow terminal widths; confirm the palette, selection, approval, blocked/error, progress, and empty/loading/error states remain consistent, readable, and free of clipped primary actions.
- [x] Recheck `git status` and ensure pre-existing user modifications and unrelated untracked files were preserved.

## Execution Handoff

The TypeScript client, API contracts, and configuration routes share interfaces,
so execute these tasks natively in order in the current session. Reinspect the
working tree before each edit because it already contains unrelated user
changes. Do not stage or commit implementation changes unless the user asks.
