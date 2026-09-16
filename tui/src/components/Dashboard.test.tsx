import { expect, test } from "bun:test";
import { testRender } from "@opentui/react/test-utils";
import { act } from "react";
import { AgentsPanel } from "./AgentsPanel";
import { PhasePanel } from "./PhasePanel";
import { StatusBar } from "./StatusBar";
import { TaskTable } from "./TaskTable";
import { App } from "../App";
import type { TramaApiClient } from "../api/client";
import type { DashboardData } from "../api/types";

const dashboard = {
  status: { status: "ok", projects: 2, queue_depth: 1, active_dispatches: 1 },
  phases: [{ phase_id: "phase-1", name: "Diseño", status: "running", progress: 50, completed_tasks: 1, total_tasks: 2 }],
  agents: [{ agent_id: "codex", active: 1, completed: 3, tasks: 4, blocked: 0 }],
  tasks: [{ task_id: "task-1", objective: "Run tests", actor: "codex", state: "running", source: "local" }],
};

function DashboardView({ data = dashboard }: { data?: typeof dashboard }) {
  return (
    <box flexDirection="column" width="100%" height="100%">
      <StatusBar status={data.status} />
      <box flexDirection="row" flexGrow={1}>
        <box flexDirection="column" width="40%">
          <PhasePanel phases={data.phases} />
          <AgentsPanel agents={data.agents} />
        </box>
        <TaskTable tasks={data.tasks} />
      </box>
    </box>
  );
}

async function renderDashboard(width: number, data?: typeof dashboard) {
  const setup = await testRender(<DashboardView data={data} />, { width, height: 24 });
  await act(async () => {
    await setup.renderOnce();
  });
  return setup;
}

async function destroy(setup: Awaited<ReturnType<typeof renderDashboard>>) {
  await act(async () => {
    setup.renderer.destroy();
  });
}

const appDashboard: DashboardData = dashboard;

async function renderApp(client: { getDashboard: () => Promise<DashboardData> }) {
  const setup = await testRender(<App client={client as unknown as TramaApiClient} pollMs={60000} />, { width: 80, height: 24 });
  await act(async () => {
    await setup.renderOnce();
  });
  return setup;
}

test("transitions from connecting to the dashboard data", async () => {
  let resolveDashboard!: (value: DashboardData) => void;
  const client = { getDashboard: () => new Promise<DashboardData>((resolve) => { resolveDashboard = resolve; }) };
  const setup = await renderApp(client);

  expect(setup.captureCharFrame()).toContain("Conectando...");
  await act(async () => {
    resolveDashboard(appDashboard);
  });
  await act(async () => {
    await setup.waitForFrame((frame) => frame.includes("Run tests"));
  });

  expect(setup.captureCharFrame()).toContain("Run tests");
  await destroy(setup as never);
});

test("shows API unavailable when loading the dashboard fails", async () => {
  const client = { getDashboard: async () => { throw new Error("offline"); } };
  const setup = await renderApp(client);

  await act(async () => {
    await setup.waitForFrame((frame) => frame.includes("API no disponible"));
  });

  expect(setup.captureCharFrame()).toContain("API no disponible");
  await destroy(setup as never);
});

test("refreshes the dashboard when r is pressed", async () => {
  let calls = 0;
  const client = { getDashboard: async () => { calls += 1; return appDashboard; } };
  const setup = await renderApp(client);
  await act(async () => {
    await setup.waitFor(() => calls === 1);
  });

  await act(async () => {
    setup.mockInput.pressKey("r");
    await setup.waitFor(() => calls === 2);
  });

  expect(calls).toBe(2);
  await destroy(setup as never);
});

test("renders the dashboard data in its panels", async () => {
  const setup = await renderDashboard(80);
  const frame = setup.captureCharFrame();

  expect(frame).toContain("TRAMA");
  expect(frame).toContain("Diseño");
  expect(frame).toContain("codex");
  expect(frame).toContain("Run tests");
  await destroy(setup);
});

test("renders a useful empty state for phases", async () => {
  const setup = await renderDashboard(80, { ...dashboard, phases: [] });

  expect(setup.captureCharFrame()).toContain("sin fases configuradas");
  await destroy(setup);
});

test("keeps the dashboard layout stable at 80 columns", async () => {
  const setup = await renderDashboard(80);

  expect(setup.captureCharFrame()).toMatchSnapshot();
  await destroy(setup);
});

test("keeps table fields and phase counters on one line at 80 columns", async () => {
  const setup = await renderDashboard(80);
  const lines = setup.captureCharFrame().split("\n");

  expect(lines.some((line) => line.includes("ESTADO") && line.includes("ORIGEN"))).toBe(true);
  expect(lines.some((line) => line.includes("Run tests") && line.includes("local"))).toBe(true);
  expect(lines.some((line) => line.includes("Diseño") && line.includes("1/2"))).toBe(true);
  await destroy(setup);
});

test("uses blocked styling for uppercase blocked states", async () => {
  const phase = dashboard.phases[0];
  const task = dashboard.tasks[0];
  if (!phase || !task) throw new Error("blocked styling fixture is incomplete");

  const setup = await renderDashboard(80, {
    ...dashboard,
    phases: [{ ...phase, status: "BLOCKED" }],
    tasks: [{ ...task, state: "BLOCKED" }],
  });
  const blockedSpans = setup.captureSpans().lines.flatMap((line) => line.spans).filter((span) => span.text.includes("!"));

  expect(blockedSpans.length).toBeGreaterThan(0);
  expect(blockedSpans.every((span) => span.fg.buffer[0] === 248 && span.fg.buffer[1] === 113 && span.fg.buffer[2] === 113)).toBe(true);
  await destroy(setup);
});

test("keeps both panel titles visible in a narrow terminal", async () => {
  const setup = await renderDashboard(48);
  const frame = setup.captureCharFrame();

  expect(frame).toContain("Fases");
  expect(frame).toContain("Tareas");
  await destroy(setup);
});
