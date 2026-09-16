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
  phases: [{ phase_id: "phase-1", name: "Diseño", status: "running", progress: 0.5, completed_tasks: 1, total_tasks: 2 }],
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

async function renderApp(client: { getDashboard: () => Promise<DashboardData> }, width = 80) {
  const setup = await testRender(<App client={client as unknown as TramaApiClient} pollMs={60000} />, { width, height: 24 });
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
    await setup.waitForVisualIdle({ quietFrames: 2 });
  });

  expect(setup.captureCharFrame()).toContain("Run tests");
  await destroy(setup as never);
});

test("shows API unavailable when loading the dashboard fails", async () => {
  let rejectDashboard!: (reason?: unknown) => void;
  const client = { getDashboard: () => new Promise<DashboardData>((_resolve, reject) => { rejectDashboard = reject; }) };
  const setup = await renderApp(client);

  await act(async () => {
    rejectDashboard(new Error("offline"));
  });
  await act(async () => {
    await setup.waitForFrame((frame) => frame.includes("API no disponible"));
  });

  expect(setup.captureCharFrame()).toContain("API no disponible");
  await destroy(setup as never);
});

test("refreshes the dashboard when r is pressed", async () => {
  let calls = 0;
  const resolvers: Array<(value: DashboardData) => void> = [];
  const client = {
    getDashboard: () => new Promise<DashboardData>((resolve) => {
      calls += 1;
      resolvers.push(resolve);
    }),
  };
  const setup = await renderApp(client);
  await act(async () => {
    await setup.waitFor(() => calls === 1);
    const resolve = resolvers.shift();
    if (!resolve) throw new Error("initial dashboard request did not register a resolver");
    resolve(appDashboard);
  });
  await act(async () => {
    await setup.waitForFrame((frame) => frame.includes("Run tests"));
  });

  await act(async () => {
    setup.mockInput.pressKey("r");
    await setup.waitFor(() => calls === 2);
    const resolve = resolvers.shift();
    if (!resolve) throw new Error("refresh dashboard request did not register a resolver");
    resolve(appDashboard);
  });
  await act(async () => {
    await setup.waitForFrame((frame) => frame.includes("Run tests"));
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

test("renders fractional phase progress as 0, 50, and 100 percent", async () => {
  const setup = await renderDashboard(80, {
    ...dashboard,
    phases: [
      { phase_id: "zero", name: "Cero", status: "planned", progress: 0, completed_tasks: 0, total_tasks: 2 },
      { phase_id: "half", name: "Mitad", status: "planned", progress: 0.5, completed_tasks: 1, total_tasks: 2 },
      { phase_id: "full", name: "Completa", status: "planned", progress: 1, completed_tasks: 2, total_tasks: 2 },
    ],
  });
  const frame = setup.captureCharFrame();

  expect(frame).toContain("Cero ░░░░░░░░░░ 0% 0/2");
  expect(frame).toContain("Mitad █████░░░░░ 50% 1/2");
  expect(frame).toContain("Completa ██████████ 100%");
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

test("renders succeeded tasks as successful", async () => {
  const task = dashboard.tasks[0];
  if (!task) throw new Error("task fixture is incomplete");

  const setup = await renderDashboard(80, { ...dashboard, tasks: [{ ...task, state: "succeeded" }] });

  expect(setup.captureCharFrame()).toContain("✓ Run tests");
  await destroy(setup);
});

test("keeps both panel titles visible in a narrow terminal", async () => {
  const setup = await renderDashboard(48);
  const frame = setup.captureCharFrame();

  expect(frame).toContain("Fases");
  expect(frame).toContain("Tareas");
  await destroy(setup);
});

test("stacks App panels at 48 columns while preserving dashboard fields", async () => {
  let resolveDashboard!: (value: DashboardData) => void;
  const client = { getDashboard: () => new Promise<DashboardData>((resolve) => { resolveDashboard = resolve; }) };
  const setup = await renderApp(client, 48);

  await act(async () => {
    resolveDashboard(appDashboard);
  });
  await act(async () => {
    await setup.waitForFrame((frame) => frame.includes("Run tests"));
    await setup.waitForVisualIdle({ quietFrames: 2 });
  });
  const frame = setup.captureCharFrame();

  expect(frame).toContain("Fases");
  expect(frame).toContain("Agentes CCCC");
  expect(frame).toContain("Tareas");
  expect(frame).toContain("ESTADO");
  expect(frame).toContain("OBJETIVO");
  expect(frame).toContain("AGENTE");
  expect(frame).toContain("ORIGEN");
  expect(frame).toContain("Run tests");
  expect(frame).toContain("1/2");
  await destroy(setup as never);
});

test("opens the command palette with slash", async () => {
  const client = { getDashboard: async () => appDashboard };
  const setup = await renderApp(client, 100);

  await act(async () => {
    await setup.waitForFrame((frame) => frame.includes("Run tests"));
  });
  setup.mockInput.pressKey("/");
  await setup.waitForFrame((frame) => frame.includes("Command palette"));

  expect(setup.captureCharFrame()).toContain("Command palette");
  await destroy(setup as never);
});

test("moves between shell screens with arrow keys", async () => {
  const client = { getDashboard: async () => appDashboard };
  const setup = await renderApp(client, 100);
  await act(async () => { await setup.waitForFrame((frame) => frame.includes("Run tests")); });
  await act(async () => { setup.mockInput.pressArrow("down"); });
  await setup.waitForFrame((frame) => frame.includes("TRAMA  ·  Projects"));
  expect(setup.captureCharFrame()).toContain("Projects");
  setup.mockInput.pressArrow("up");
  await setup.waitForFrame((frame) => frame.includes("TRAMA  ·  Dashboard"));
  expect(setup.captureCharFrame()).toContain("Dashboard");
  await destroy(setup as never);
});

test("opens the selected task timeline with Enter", async () => {
  const tasksDashboard: DashboardData = {
    ...appDashboard,
    tasks: [
      ...appDashboard.tasks,
      { task_id: "task-2", objective: "Deploy", actor: "hermes", state: "queued", source: "local" },
    ],
  };
  const client = {
    getDashboard: async () => tasksDashboard,
    getTaskTimeline: async (taskId: string) => [{ entry_id: "entry-1", kind: "event", sequence: 1, actor: "system", action: `${taskId}.accepted`, status: "accepted" }],
  };
  const setup = await renderApp(client, 100);
  await act(async () => { await setup.waitForFrame((frame) => frame.includes("Run tests")); });
  await act(async () => { setup.mockInput.pressArrow("down"); });
  await setup.waitForFrame((frame) => frame.includes("Projects"));
  await act(async () => { setup.mockInput.pressArrow("down"); });
  await setup.waitForFrame((frame) => frame.includes("Tasks"));
  await setup.waitForVisualIdle({ quietFrames: 2 });
  await act(async () => { setup.mockInput.pressArrow("down"); });
  await setup.waitForFrame((frame) => frame.includes("Deploy") && frame.includes("[Enter detalle]"));
  await act(async () => { setup.mockInput.pressEnter(); });
  await setup.waitForFrame((frame) => frame.includes("Timeline"));
  expect(setup.captureCharFrame()).toContain("task-2.accepted");
  setup.mockInput.pressEscape();
  await setup.waitForFrame((frame) => frame.includes("TRAMA  ·  Tasks"));
  await destroy(setup as never);
});

test("leaves Tasks at the list boundaries with arrow keys", async () => {
  const client = { getDashboard: async () => appDashboard };
  const setup = await renderApp(client, 100);
  await act(async () => { await setup.waitForFrame((frame) => frame.includes("Run tests")); });
  await act(async () => { setup.mockInput.pressArrow("down"); });
  await setup.waitForFrame((frame) => frame.includes("Projects"));
  await act(async () => { setup.mockInput.pressArrow("down"); });
  await setup.waitForFrame((frame) => frame.includes("Tasks"));
  await act(async () => { setup.mockInput.pressArrow("up"); });
  await setup.waitForFrame((frame) => frame.includes("TRAMA  ·  Projects"));
  await destroy(setup as never);
});

test("keeps screen navigation available when Tasks is empty", async () => {
  const client = { getDashboard: async () => ({ ...appDashboard, tasks: [] }) };
  const setup = await renderApp(client, 100);
  await act(async () => { await setup.waitForFrame((frame) => frame.includes("TRAMA  ·  Dashboard")); });
  await act(async () => { setup.mockInput.pressArrow("down"); });
  await setup.waitForFrame((frame) => frame.includes("TRAMA  ·  Projects"));
  await act(async () => { setup.mockInput.pressArrow("down"); });
  await setup.waitForFrame((frame) => frame.includes("TRAMA  ·  Tasks"));
  await act(async () => { setup.mockInput.pressArrow("up"); });
  await setup.waitForFrame((frame) => frame.includes("TRAMA  ·  Projects"));
  await destroy(setup as never);
});

test("shows the shell title and keyboard hints at a narrow width", async () => {
  const client = { getDashboard: async () => appDashboard };
  const setup = await renderApp(client, 48);

  await act(async () => {
    await setup.waitForFrame((frame) => frame.includes("Run tests"));
    await setup.waitForVisualIdle({ quietFrames: 2 });
  });

  const frame = setup.captureCharFrame();
  expect(frame).toContain("Dashboard");
  expect(frame).toContain("[r]");
  await destroy(setup as never);
});

test("keeps the last dashboard projection when a refresh fails", async () => {
  let calls = 0;
  const client = {
    getDashboard: async () => {
      calls += 1;
      if (calls > 1) throw new Error("offline");
      return appDashboard;
    },
  };
  const setup = await renderApp(client);
  await act(async () => { await setup.waitForFrame((frame) => frame.includes("Run tests")); });
  setup.mockInput.pressKey("r");
  await setup.waitForFrame((frame) => frame.includes("obsoletos"));
  const frame = setup.captureCharFrame();
  expect(frame).toContain("Run tests");
  expect(frame).toContain("obsoletos");
  await destroy(setup as never);
});
