# TypeScript TRAMA TUI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Build a Bun/TypeScript/OpenTUI React dashboard that consumes the local TRAMA API while preserving the existing Python TUI as fallback.

**Architecture:** Add an independent tui/ package. Its HTTP client owns transport, timeout, and DTO normalization; React/OpenTUI components only render dashboard state. The first release is read-only, polls /v1/status and /v1/overview, and launches with bun run --cwd tui start.

**Tech Stack:** Bun, TypeScript, React, @opentui/core, @opentui/react, bun:test, and @opentui/react/test-utils.

**Spec:** docs/superpowers/specs/2026-09-15-tui-typescript-design.md

## Global Constraints

- The Python API remains the source of truth for state, contracts, and business rules.
- Keep the API bound to 127.0.0.1; default the client to http://127.0.0.1:8090.
- Use Bun commands for OpenTUI; do not substitute Node, npm, Jest, or dotenv patterns.
- Use renderer.destroy() for terminal cleanup; never call process.exit() directly.
- Keep trama tui and the Textual implementation unchanged in this phase.
- Do not change versioned API contracts for this read-only client.
- Preserve unrelated user changes and stage only files belonging to the current task.

---

## File Map

- Create tui/package.json: Bun scripts and dependencies.
- Create tui/tsconfig.json: TypeScript JSX/module configuration.
- Create tui/src/index.tsx: renderer, client, React root, and cleanup wiring.
- Create tui/src/App.tsx: polling lifecycle, keyboard shortcuts, and composition.
- Create tui/src/api/types.ts: DTOs and normalized dashboard model.
- Create tui/src/api/client.ts: typed HTTP calls and timeout handling.
- Create tui/src/components/StatusBar.tsx: status line.
- Create tui/src/components/PhasePanel.tsx: phase progress.
- Create tui/src/components/AgentsPanel.tsx: CCCC counters.
- Create tui/src/components/TaskTable.tsx: read-only queue.
- Create tui/src/components/Dashboard.test.tsx: headless render and interaction tests.
- Modify README.md: new launcher instructions; retain trama tui.

## Task 1: Verify Bun and scaffold the isolated package

**Files:**

- Create: tui/package.json
- Create: tui/tsconfig.json
- Create: tui/src/index.tsx
- Test: tui/src/smoke.test.tsx

**Interfaces:**

- Produces bun run --cwd tui start and bun test --cwd tui.
- The entry point creates an OpenTUI CLI renderer, renders React App, and never exits through process.exit().

- [ ] **Step 1: Check prerequisites without installing global tools**

Run:

    Get-Command bun -ErrorAction SilentlyContinue
    Get-Command zig -ErrorAction SilentlyContinue

Expected: Bun is available. If OpenTUI installation requires Zig and Zig is absent, report it instead of changing global Windows tooling.

- [ ] **Step 2: Generate the supported React scaffold**

Only when tui/ does not exist, run:

    bunx create-tui@latest -t react tui

The template option must precede the directory argument and the command must remain non-interactive.

- [ ] **Step 3: Configure scripts and add the smoke test**

Ensure tui/package.json has scripts equivalent to:

    {
      "scripts": {
        "start": "bun run src/index.tsx",
        "test": "bun test"
      }
    }

Add a test using testRender(<text>TRAMA</text>, { width: 20, height: 5 }), call renderOnce(), assert the captured frame contains TRAMA, and destroy the renderer.

- [ ] **Step 4: Install and test**

    bun install --cwd tui
    bun test --cwd tui

Expected: the smoke test passes. Do not replace Bun with Node if native dependencies fail.

- [ ] **Step 5: Commit only the scaffold**

    git add tui/package.json tui/tsconfig.json tui/src/index.tsx tui/src/smoke.test.tsx tui/bun.lockb tui/bun.lock
    git commit -m "feat: scaffold Bun OpenTUI client"

Stage only the lockfile that Bun creates.

## Task 2: Implement the typed API client

**Files:**

- Create: tui/src/api/types.ts
- Create: tui/src/api/client.ts
- Test: tui/src/api/client.test.ts

**Interfaces:**

- new TramaApiClient(baseUrl: string, fetchImpl?: typeof fetch, timeoutMs?: number)
- getStatus(): Promise<Status>
- getOverview(): Promise<Overview>
- getTasks(): Promise<Task[]>
- getDashboard(): Promise<DashboardData>
- ApiError extends Error with status: number | undefined and endpoint: string.

- [ ] **Step 1: Write failing fake-fetch tests**

Cover these cases:

    test("combines status, overview, and agents", async () => {
      const client = new TramaApiClient(baseUrl, fakeFetch(fixtures))
      await expect(client.getDashboard()).resolves.toEqual(expectedDashboard)
    })

    test("falls back to /v1/tasks when overview has no queue", async () => {
      const client = new TramaApiClient(baseUrl, fakeFetch({ overview: overviewWithoutQueue, tasks }))
      await expect(client.getDashboard()).resolves.toMatchObject({ tasks })
    })

    test("converts non-2xx responses to ApiError", async () => {
      const client = new TramaApiClient(baseUrl, fakeFetchError(503))
      await expect(client.getStatus()).rejects.toMatchObject({
        status: 503, endpoint: "/v1/status"
      })
    })

The fake fetch must record URL and receive an AbortSignal, so tests verify the base URL and timeout path.

- [ ] **Step 2: Define DTOs matching the observed API**

Define Status, Phase, Agent, Task, Overview, and DashboardData. Use optional fields for values the API may omit:

    type Status = { status?: string; projects?: number; queue_depth?: number; active_dispatches?: number }
    type Phase = { phase_id: string; name?: string; status?: string; progress?: number; completed_tasks?: number; total_tasks?: number }
    type Agent = { agent_id: string; active?: number; completed?: number; tasks?: number; blocked?: number }
    type Task = { task_id: string; objective?: string; actor?: string; state?: string; source?: string }
    type Overview = { phases?: Phase[]; queue?: Task[]; agents?: Agent[] }
    type DashboardData = { status: Status; phases: Phase[]; agents: Agent[]; tasks: Task[] }

- [ ] **Step 3: Implement transport, timeout, validation, and fallback**

Use the injected fetch function, AbortController, and response.ok. Reject transport errors, invalid JSON, non-object payloads, and non-2xx responses. getDashboard() must call /v1/status and /v1/overview, use overview.queue when it is an array, otherwise call /v1/tasks, and normalize missing arrays to [].

- [ ] **Step 4: Run and commit**

    bun test --cwd tui src/api/client.test.ts
    git add tui/src/api
    git commit -m "feat: add typed TRAMA API client"

## Task 3: Build the read-only dashboard components

**Files:**

- Create: tui/src/components/StatusBar.tsx
- Create: tui/src/components/PhasePanel.tsx
- Create: tui/src/components/AgentsPanel.tsx
- Create: tui/src/components/TaskTable.tsx
- Create: tui/src/components/Dashboard.test.tsx

**Interfaces:**

- StatusBar({ status }: { status: Status })
- PhasePanel({ phases }: { phases: Phase[] })
- AgentsPanel({ agents }: { agents: Agent[] })
- TaskTable({ tasks }: { tasks: Task[] })

- [ ] **Step 1: Write failing component tests**

Render at 80x24 and assert the frame contains TRAMA, Diseño, codex, and Run tests. Render empty data and assert sin fases configuradas. Add a stable 80x24 snapshot and a 48x24 assertion that both panel titles remain visible.

- [ ] **Step 2: Implement OpenTUI JSX components**

Use <box> for panels and <text> for content. Use nested text modifiers for emphasis and color. Render fixed-width progress bars and map states to ›, !, ✓, and ○. Never render undefined values or object stringification.

- [ ] **Step 3: Run tests and commit**

    bun test --cwd tui src/components/Dashboard.test.tsx
    git add tui/src/components
    git commit -m "feat: render TRAMA dashboard in OpenTUI"

## Task 4: Wire polling, keyboard controls, and errors

**Files:**

- Modify: tui/src/App.tsx
- Modify: tui/src/index.tsx
- Modify: tui/src/components/Dashboard.test.tsx

**Interfaces:**

- App({ client, pollMs = 2000 }: { client: TramaApiClient; pollMs?: number })
- State is loading | ready | error, with dashboard data on ready and an Error on error.

- [ ] **Step 1: Write failing behavior tests**

Test that a fake client transitions from conectando to real task data, a rejection shows API unavailable, and emitting the r key calls getDashboard again. Use pollMs={60000} in tests so the interval cannot create extra calls.

- [ ] **Step 2: Implement App lifecycle**

Use useState, useEffect, and useKeyboard. Fetch once on mount, schedule a 2-second interval, clear it on unmount, and guard against overlapping requests. Route r through the same refresh function. Route q through useRenderer and renderer.destroy().

- [ ] **Step 3: Wire the production entry point**

Instantiate TramaApiClient(process.env.TRAMA_API_URL ?? "http://127.0.0.1:8090"), create the CLI renderer, and render <App client={client} />. Do not add dotenv or a Node runtime.

- [ ] **Step 4: Run and commit**

    bun test --cwd tui
    git add tui/src/App.tsx tui/src/index.tsx tui/src/components/Dashboard.test.tsx
    git commit -m "feat: add TRAMA TUI polling and controls"

## Task 5: Document and verify the migration

**Files:**

- Modify: README.md
- Verify: src/trama_platform/cli.py, src/trama_platform/tui.py, tests/test_tui.py

- [ ] **Step 1: Document the new launcher**

Add near the existing TUI instructions:

    .\.venv\Scripts\python.exe -m trama_platform api --host 127.0.0.1 --port 8090
    bun install --cwd tui
    bun run --cwd tui start

Document TRAMA_API_URL and state that trama tui remains the Python fallback.

- [ ] **Step 2: Verify documented commands**

    rg -n "bun (install|run).*tui|trama tui|TRAMA_API_URL" README.md tui/package.json

Expected: each documented command matches a package script or existing Python CLI command.

- [ ] **Step 3: Run regression and Bun tests**

    .\.venv\Scripts\python.exe -m pytest -q
    bun test --cwd tui
    git diff --check
    git status --short

Expected: Python and Bun tests pass, no whitespace errors exist, and unrelated changes remain unstaged.

- [ ] **Step 4: Perform manual acceptance**

Run the API and bun run --cwd tui start in separate terminals. Confirm real status, phases, specialists, and tasks render; r refreshes; q restores the terminal; and trama tui still launches Textual.

- [ ] **Step 5: Commit documentation**

    git add README.md
    git commit -m "docs: document TypeScript TRAMA TUI"
