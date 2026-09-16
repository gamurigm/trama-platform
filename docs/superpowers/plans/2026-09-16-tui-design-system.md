# TRAMA TUI Design System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve `tui/` from its current four-panel read-only dashboard into a navigable OpenTUI React operations cockpit for projects, tasks, agents, queues, workers, events, memory and system health.

**Architecture:** Keep OpenTUI as the only interactive renderer. Add typed API methods, a pure navigation reducer, reusable visual primitives, domain screens, and an AppShell that owns polling and overlays. The Python Textual TUI and backend contracts remain unchanged.

**Tech Stack:** Bun, TypeScript, React 19, `@opentui/core`, `@opentui/react`, `bun:test`, `@opentui/react/test-utils`, and the already installed terminal utilities only outside the OpenTUI render tree.

**Spec:** `docs/superpowers/specs/2026-09-16-tui-design-system-design.md`

## Global Constraints

- The Python API remains the source of truth.
- `trama tui` remains the Python fallback.
- OpenTUI is the only interactive renderer; Ink is not mounted inside the OpenTUI tree.
- Every project-scoped request preserves `project_id`; results from different projects are never combined.
- Missing backend fields render as `no disponible`; the TUI never invents metrics.
- The default API URL remains `http://127.0.0.1:8090`; do not widen the API binding.
- Refresh failures retain the last valid projection, mark it stale, and expose retry.
- Approve, cancel and retry require contextual confirmation before sending a request.
- Do not add WebSocket, streaming, backend contract changes or a replacement for `trama tui`.
- Use `renderer.destroy()` for cleanup and never `process.exit()`.
- Use `bun:test` and `@opentui/react/test-utils` for TUI tests.
- Preserve existing dirty changes and stage only files belonging to the current task.

## File Map

- `tui/src/api/types.ts`: DTOs and normalized UI models.
- `tui/src/api/client.ts`: HTTP methods, timeout, parsing and typed errors.
- `tui/src/navigation/model.ts`: route, project, focus, selection and overlay state.
- `tui/src/navigation/reducer.ts`: pure keyboard transitions.
- `tui/src/ui/`: tokens, panels, badges, hints, palette and confirmation dialog.
- `tui/src/screens/`: dashboard plus one screen per operational domain.
- `tui/src/App.tsx`: AppShell, polling, routes and lifecycle.

---

### Task 1: Add typed operations data and the navigation reducer

**Files:**

- Modify: `tui/src/api/types.ts`
- Modify: `tui/src/api/client.ts`
- Create: `tui/src/navigation/model.ts`
- Create: `tui/src/navigation/reducer.ts`
- Test: `tui/src/navigation/reducer.test.ts`
- Test: `tui/src/api/client.test.ts`

**Interfaces:**

- `ScreenId = "dashboard" | "projects" | "tasks" | "agents" | "queues" | "workers" | "events" | "memory" | "health"`.
- `NavigationState = { screen: ScreenId; projectId?: string; selectedIndex: number; selectedId?: string; overlay: "none" | "palette" | "help" | "project-picker" | "confirm"; filter: string; notice?: Notice }`.
- `reduceNavigation(state, action): NavigationState` is pure.
- Client methods: `listProjects`, `getHealth`, `getOverview`, `listEvents`, `listLogs`, `getTaskTimeline`, `approveTask`, `cancelTask` and `retryTask`.

- [ ] **Step 1: Write the failing reducer tests.**

```tsx
import { expect, test } from "bun:test";
import { initialNavigation, reduceNavigation } from "./reducer";

test("moves with j and wraps at the end", () => {
  const next = reduceNavigation({ ...initialNavigation, selectedIndex: 2 }, { type: "key", key: "j", itemCount: 3 });
  expect(next.selectedIndex).toBe(0);
});

test("keeps project context but clears screen-local selection", () => {
  const next = reduceNavigation({ ...initialNavigation, projectId: "demo", selectedId: "task-1" }, { type: "open-screen", screen: "events" });
  expect(next).toMatchObject({ screen: "events", projectId: "demo", selectedId: undefined });
});
```

- [ ] **Step 2: Run the focused test and verify the expected missing-module failure.**

Run: `bun test --cwd tui src/navigation/reducer.test.ts`

Expected: FAIL because `src/navigation/reducer.ts` does not exist.

- [ ] **Step 3: Implement the reducer and model.**

Handle ArrowUp/ArrowDown and `j/k`, Enter, Escape, slash, question mark,
project selection, filtering and notice transitions. The reducer must not call
the API or renderer.

- [ ] **Step 4: Extend the client with endpoint-specific DTO validation.**

Add project, health, event, log, timeline and action types. Reuse the current
timeout and `ApiError` behavior, build query strings with
`URLSearchParams`, omit undefined filters and preserve endpoint names in
errors.

- [ ] **Step 5: Run the foundation tests and commit.**

Run: `bun test --cwd tui src/navigation/reducer.test.ts src/api/client.test.ts`

Expected: PASS.

```powershell
git add tui/src/api tui/src/navigation
git commit -m "feat: add TUI navigation and typed operations model"
```

### Task 2: Build reusable terminal visual primitives

**Files:**

- Create: `tui/src/ui/tokens.ts`
- Create: `tui/src/ui/Panel.tsx`
- Create: `tui/src/ui/StatusBadge.tsx`
- Create: `tui/src/ui/KeyHints.tsx`
- Create: `tui/src/ui/ConfirmDialog.tsx`
- Test: `tui/src/ui/Primitives.test.tsx`

**Interfaces:**

- `tokens` exports `colors`, `spacing`, `borders` and `density`.
- `Panel({ title, accent, children, flexGrow, width })` renders a bordered region.
- `StatusBadge({ state, label })` renders symbol plus text.
- `KeyHints({ items })` renders footer shortcuts.
- `ConfirmDialog({ action, target, consequence, onConfirm, onCancel })` owns no API calls.

- [ ] **Step 1: Write a failing primitive render test.**

```tsx
test("renders a titled panel and explicit blocked status", async () => {
  const setup = await testRender(
    <box flexDirection="column">
      <Panel title="Queues" accent="attention"><text>queue depth: 2</text></Panel>
      <StatusBadge state="blocked" label="blocked" />
    </box>,
    { width: 40, height: 8 },
  );
  await act(async () => { await setup.renderOnce(); });
  expect(setup.captureCharFrame()).toContain("! blocked");
  await act(async () => { setup.renderer.destroy(); });
});
```

- [ ] **Step 2: Run the test and verify it fails because primitives are absent.**

Run: `bun test --cwd tui src/ui/Primitives.test.tsx`

Expected: FAIL with missing primitive modules.

- [ ] **Step 3: Implement the approved palette and state cues.**

Use `#07111F`, `#10253A`, `#E8F1F8`, `#63E6E2`,
`#B8A1FF` and `#FFB454`. Use `!`, `✓`, `›`,
`○` and `·` with text for blocked, succeeded, active, pending and
unavailable. The selected row receives a visible cian marker.

- [ ] **Step 4: Implement the confirmation dialog.**

The dialog displays action, target and consequence. Enter or `y` confirms;
Escape or `n` cancels; neither callback runs during render. Focus remains
inside the dialog until a decision is made.

- [ ] **Step 5: Run tests, typecheck and commit.**

Run: `bun test --cwd tui src/ui/Primitives.test.tsx` and
`tui/node_modules/.bin/tsc.cmd --noEmit -p tui/tsconfig.json`.

Expected: both exit 0.

```powershell
git add tui/src/ui
git commit -m "feat: add TRAMA TUI visual primitives"
```

### Task 3: Replace the fixed layout with AppShell and Dashboard

**Files:**

- Modify: `tui/src/App.tsx`
- Modify: `tui/src/index.tsx`
- Create: `tui/src/ui/CommandPalette.tsx`
- Create: `tui/src/screens/NavigationRail.tsx`
- Create: `tui/src/screens/DashboardScreen.tsx`
- Create: `tui/src/screens/ActivityPanel.tsx`
- Modify: `tui/src/components/Dashboard.test.tsx`

**Interfaces:**

- AppShell owns `NavigationState`, last-good data, polling, stale state and overlays.
- `CommandPalette({ query, commands, onChoose, onClose })` filters and selects commands.
- `DashboardScreen({ data, selectedId, onSelect })` renders summary, phases, queues/workers and activity.
- `NavigationRail({ screen, onChoose })` renders all nine screens.

- [ ] **Step 1: Add failing tests for palette, route changes and narrow layout.**

```tsx
test("opens the palette with slash and navigates to Events", async () => {
  const setup = await renderApp(client, 100);
  await resolveDashboardAndWait(setup);
  setup.mockInput.pressKey("/");
  expect(setup.captureCharFrame()).toContain("Command palette");
  setup.mockInput.write("events");
  setup.mockInput.pressKey("ENTER");
  expect(setup.captureCharFrame()).toContain("Events");
  await destroy(setup);
});
```

- [ ] **Step 2: Run the dashboard tests and verify the new test fails.**

Run: `bun test --cwd tui src/components/Dashboard.test.tsx`

Expected: FAIL because the current App has no routes or command palette.

- [ ] **Step 3: Implement AppShell polling and layout.**

Keep the current loading and error behavior as sub-states of the shell. Add
last-good data, last-updated time, refreshing state and stale notices. Prevent
overlapping requests and pause polling while an overlay is open. Use the
approved header, rail, content and footer; below 60 columns stack content
without hiding essential labels.

- [ ] **Step 4: Implement command palette and route selection.**

Expose the nine screens plus refresh, project selection, help and quit. Route
selection closes the overlay and resets only screen-local selection.

- [ ] **Step 5: Run the existing and new dashboard tests, then commit.**

Run: `bun test --cwd tui src/components/Dashboard.test.tsx`.

Expected: PASS, including loading, error, refresh and narrow-layout behavior.

```powershell
git add tui/src/App.tsx tui/src/index.tsx tui/src/ui/CommandPalette.tsx tui/src/screens tui/src/components/Dashboard.test.tsx
git commit -m "feat: add navigable TRAMA TUI shell"
```

### Task 4: Implement the operational screens and details

**Files:**

- Create: `tui/src/screens/ProjectsScreen.tsx`
- Create: `tui/src/screens/TasksScreen.tsx`
- Create: `tui/src/screens/AgentsScreen.tsx`
- Create: `tui/src/screens/QueuesScreen.tsx`
- Create: `tui/src/screens/WorkersScreen.tsx`
- Create: `tui/src/screens/EventsScreen.tsx`
- Create: `tui/src/screens/MemoryScreen.tsx`
- Create: `tui/src/screens/HealthScreen.tsx`
- Create: `tui/src/screens/DetailScreen.tsx`
- Test: `tui/src/screens/Screens.test.tsx`

**Interfaces:**

- Every screen receives `projectId`, typed data, `selectedId`, `onSelect` and `onOpenDetail`.
- `TasksScreen` emits `onAction(taskId, "approve" | "cancel" | "retry")`.
- `DetailScreen({ kind, id, timeline })` renders stable timeline entries.

- [ ] **Step 1: Write failing tests for data, empty and unavailable states.**

```tsx
test("renders a project context and title for every screen", async () => {
  for (const screen of screenIds) {
    const setup = await renderScreen(screen, { projectId: "demo" });
    expect(setup.captureCharFrame()).toContain("demo");
    expect(setup.captureCharFrame()).toContain(screenTitles[screen]);
    await destroy(setup);
  }
});

test("does not invent worker metrics", async () => {
  const setup = await renderScreen("workers", { status: { status: "ok" } });
  expect(setup.captureCharFrame()).toContain("no disponible");
  await destroy(setup);
});
```

- [ ] **Step 2: Run the screen test and verify missing-module failure.**

Run: `bun test --cwd tui src/screens/Screens.test.tsx`.

Expected: FAIL because the screen modules do not exist.

- [ ] **Step 3: Implement screen components using shared primitives.**

Use stable IDs, short labels, terminal-width truncation and explicit empty
messages. Do not create one polling loop per screen; AppShell owns refresh.

- [ ] **Step 4: Load screen data with project isolation.**

Load projects when the picker opens, events/logs/memory on screen entry and a
timeline only after Enter opens a detail. Include active `project_id` on
project-scoped requests. Keep a list mounted when detail loading fails.

- [ ] **Step 5: Run width fixtures and commit.**

Run: `bun test --cwd tui src/screens/Screens.test.tsx`.

Expected: PASS at 100×30, 80×24 and 48×24.

```powershell
git add tui/src/screens
git commit -m "feat: add TRAMA operational screens"
```

### Task 5: Add safe actions and stale/error recovery

**Files:**

- Modify: `tui/src/App.tsx`
- Modify: `tui/src/api/client.ts`
- Modify: `tui/src/navigation/model.ts`
- Modify: `tui/src/navigation/reducer.ts`
- Modify: `tui/src/ui/ConfirmDialog.tsx`
- Test: `tui/src/components/Dashboard.test.tsx`
- Test: `tui/src/api/client.test.ts`

**Interfaces:**

- `ActionRequest = { taskId: string; action: "approve" | "cancel" | "retry" }`.
- `Notice = { kind: "info" | "success" | "warning" | "error"; message: string }`.

- [ ] **Step 1: Write failing tests for confirmation and stale recovery.**

```tsx
test("does not cancel until confirmation is accepted", async () => {
  const setup = await renderTaskScreenWithAction("task-1", "cancel");
  setup.mockInput.pressKey("x");
  expect(setup.captureCharFrame()).toContain("Confirmar cancelar");
  expect(client.cancelTask).not.toHaveBeenCalled();
  setup.mockInput.pressKey("n");
  expect(client.cancelTask).not.toHaveBeenCalled();
  await destroy(setup);
});

test("keeps last data and marks it stale after refresh failure", async () => {
  const setup = await renderApp(client);
  await resolveDashboardAndWait(setup);
  client.getDashboard = async () => { throw new Error("offline"); };
  setup.mockInput.pressKey("r");
  await act(async () => { await setup.waitForFrame((frame) => frame.includes("obsoletos")); });
  expect(setup.captureCharFrame()).toContain("Run tests");
  await destroy(setup);
});
```

- [ ] **Step 2: Run the focused tests and verify the expected failure.**

Run: `bun test --cwd tui src/components/Dashboard.test.tsx src/api/client.test.ts`.

Expected: FAIL because action overlays and stale state are absent.

- [ ] **Step 3: Implement POST actions and confirmation sequencing.**

Send approve, cancel or retry only after Enter/`y`. Send no optimistic task
transition. Convert non-2xx responses to `ApiError` and report the result
as a notice.

- [ ] **Step 4: Implement last-good projection and recoverable errors.**

On refresh failure retain the projection, set `staleSince`, show the
endpoint message and keep `r` available. Clear stale state only after a
successful refresh. Pause refresh while palette or dialog is open.

- [ ] **Step 5: Run all TUI tests, typecheck and commit.**

Run: `bun test --cwd tui` and
`tui/node_modules/.bin/tsc.cmd --noEmit -p tui/tsconfig.json`.

Expected: all tests and typecheck pass.

```powershell
git add tui/src/App.tsx tui/src/api/client.ts tui/src/navigation tui/src/ui/ConfirmDialog.tsx tui/src/components/Dashboard.test.tsx tui/src/api/client.test.ts
git commit -m "feat: add safe TUI actions and recovery states"
```

### Task 6: Document and verify the completed cockpit

**Files:**

- Modify: `README.md`
- Modify: `docs/ARQUITECTURA.md`
- Test: `tui/src/components/Dashboard.test.tsx`

- [ ] **Step 1: Document launch, API URL, project context and shortcuts.**

Document `bun install --cwd tui`, `bun run --cwd tui start`,
`TRAMA_API_URL`, `trama tui` as fallback and the complete key map.
Do not add credentials or change the local bind policy.

- [ ] **Step 2: Add snapshots at 100×30, 80×24 and 48×24.**

Assert that header, rail, selected row, status symbols, footer and essential
task fields remain visible at all widths.

- [ ] **Step 3: Run the complete verification set.**

Run:

```powershell
bun test --cwd tui
tui/node_modules/.bin/tsc.cmd --noEmit -p tui/tsconfig.json
.\\.venv\\Scripts\\python.exe -m pytest -q
git diff --check
```

Expected: all four commands exit 0. If Bun remains unavailable, report that
exact blocker and do not claim the Bun tests passed.

- [ ] **Step 4: Inspect and stage only the intended files.**

Run `git diff --stat`, `git status --short` and
`git diff --name-only`. Leave existing `AGENTS.md`,
`arq_v3.md` and unrelated local changes untouched.

- [ ] **Step 5: Commit the final implementation and docs.**

```powershell
git add README.md docs/ARQUITECTURA.md tui
git commit -m "feat: complete TRAMA TUI operations cockpit"
```
