# TRAMA TypeScript TUI Design

**Status:** Approved in conversation; awaiting review of this written specification.

## Goal

Make the TypeScript OpenTUI application the only TRAMA TUI. Let an operator
manage TRAMA projects, planning, approvals, tasks, runtime settings, and
integration diagnostics from that interface, while retaining the Python API
and control plane.

## User intent and current state

The operator wants to create and manage requirements, phases, plans, and tasks
from the terminal UI, inspect the connected tools, and configure integrations
there as well. The global `trama` command should open this interface.

The current TypeScript TUI is a read-only dashboard. The Python Textual TUI is
also read-only. The FastAPI control plane already supports most project,
requirement, phase, task, approval, timeline, and log operations, but the
TypeScript client does not expose them all and the UI has no entry forms.

On the inspected machine, Hermes is unavailable: `hermes` is not on `PATH`,
`uv tool list` reports no installed tools, and the expected Hermes configuration
file is absent. CCCC 0.4.39 is installed but its daemon is stopped. TRAMA is
configured with the `memory` coordination backend, so it is not currently
dispatching work to CCCC.

## Product behavior

### Navigation and operations

The TypeScript TUI provides these views:

- **Overview:** API state, projects, phases, task queue, agents, recent
  activity, and clear empty/error states.
- **Projects:** list, inspect, and register projects.
- **Planning:** list and register requirements and phases; show dependencies;
  list plan proposals; create proposals when needed; and approve them only
  after an explicit human action.
- **Tasks:** list and inspect tasks; submit tasks with project, objective,
  actor, repository, branch, worktree, paths, dependencies, and acceptance
  criteria; approve planned tasks; cancel or retry tasks with confirmation.
- **Observability:** open task/phase timelines and filter sanitized logs by
  project, requirement, phase, task, and severity.
- **Integrations and configuration:** inspect configuration source and
  readiness for the integrations currently recognized by TRAMA; edit supported
  settings; enter, replace, or clear credentials; test connections; inspect
  MCP tools; and explicitly start/stop the CCCC daemon when CCCC is installed.

The UI uses keyboard-first navigation and OpenTUI input/textarea controls.
Every operation reports success or a useful API/validation error in the
interface. Approval remains a separate, explicit action. Configuration changes
that require a process restart are shown as pending until the operator applies
them.

### Integration status and configuration

Show status as distinct states such as **connected**, **configured but
unreachable**, **not configured**, **not installed**, **stopped**, and **not
implemented**. A saved URL or token alone must never be reported as a working
connection.

Cover settings already represented by TRAMA for CCCC coordination, Hermes/MCP,
Semantica, Utopia, Colibri, the task gateway, NATS, and general API/runtime
configuration. For features that do not yet have an operational adapter (for
example, model listing currently returns `not_configured`), show the setting
and the actual limitation instead of implying that the integration works.

Hermes configuration can set its executable and config path and add/update only
TRAMA's MCP server entry. Preserve all unrelated Hermes configuration. Display
the TRAMA MCP tool inventory and distinguish tools exposed by TRAMA from tools
enabled in Hermes. A missing Hermes executable is reported; the TUI does not
install it.

### Configuration storage and secret handling

- Store non-secret, per-user settings outside the repository, under
  `%LOCALAPPDATA%\TRAMA\`.
- Store tokens and passwords in Windows Credential Manager. Do not put secrets
  in the settings file, repository, terminal history, status output, API
  responses, exception text, or logs.
- Mask secret fields in the TUI. Support replacing and clearing a secret
  without displaying its current value.
- Environment variables override saved user settings. Show which source is
  active for each setting; do not silently change the user's environment.
- Restart the TRAMA-managed API only after an explicit operator action when a
  setting needs restart. Never restart an unrelated process.
- Connection checks must use configured values without echoing credentials.

## Architecture

The TypeScript OpenTUI application is the sole interface implementation. It
uses the existing Python FastAPI control plane as the source of truth and a
typed TypeScript API client for queries and mutations. Add narrowly scoped API
operations for missing list/configuration/diagnostic behavior; do not create a
second business-data store in the TUI.

Keep Python as the API, domain runtime, CLI, and integration adapter layer.
Change `trama tui` into a launcher for the TypeScript app. Change the global
`trama` shim so a bare `trama` starts the TRAMA-managed API if needed and opens
the same TypeScript TUI from any working directory. Keep other CLI subcommands
forwarded to the Python CLI.

Remove the Python Textual app, its dedicated tests, and the `textual` runtime
dependency. Update the README so it documents one TUI and its controls.

## Safety and operational constraints

- Keep the API bound to `127.0.0.1` by default.
- Keep human approval mandatory for plans and planned tasks.
- Keep CCCC, Hermes, memory, and external-service actions explicit and visible.
- Never claim a connector is healthy based only on saved configuration.
- Do not install Hermes or other external tools from this feature.
- Preserve existing TRAMA database contracts and existing user changes in the
  working tree.

## Acceptance criteria

1. `trama` from outside the repository starts the managed API if required and
   opens the TypeScript TUI; `trama tui` opens the same UI.
2. The TUI can register and inspect a project, create a requirement and phases,
   inspect/create/approve a plan proposal, and submit/approve/cancel/retry tasks
   using the existing control plane.
3. The TUI can inspect timelines, logs, phases, task queue, and agents, and
   errors are visible without exposing secrets.
4. The TUI can edit supported per-user connector settings, protect credentials
   in Windows Credential Manager, test available connections, and distinguish
   configured state from actual health.
5. Hermes is shown as not installed on the inspected machine, its configuration
   can be prepared without clobbering unrelated Hermes settings, and no install
   is attempted.
6. CCCC is shown as installed with its daemon stopped and memory coordination
   active until the operator changes that configuration.
7. The Python Textual implementation and its dedicated test file are removed;
   no duplicate Python TUI remains.
8. The TypeScript UI build/type validation and manual terminal flows succeed.

## Out of scope

- Installing or upgrading Hermes, CCCC, Bun, or other external programs.
- Arbitrary third-party connector plugins not represented in TRAMA settings.
- Automatically approving plans or tasks, or enabling unattended execution.
- Changing project code, repositories, or external systems from a settings
  screen without an explicit task/operation.

## Review notes

- The settings screen must identify values overridden by environment variables
  so a saved value cannot appear ineffective without explanation.
- Local configuration and API status must remain useful when optional
  integrations are absent.
- Hermes YAML updates must preserve unrelated fields and retain manual approval
  policy.
