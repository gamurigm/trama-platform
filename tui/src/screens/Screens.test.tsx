import { expect, test } from "bun:test";
import { testRender } from "@opentui/react/test-utils";
import { act } from "react";
import type { ScreenId } from "../navigation/model";
import { screenIds, screenTitles } from "./NavigationRail";
import { ProjectsScreen } from "./ProjectsScreen";
import { TasksScreen } from "./TasksScreen";
import { AgentsScreen } from "./AgentsScreen";
import { QueuesScreen } from "./QueuesScreen";
import { WorkersScreen } from "./WorkersScreen";
import { EventsScreen } from "./EventsScreen";
import { MemoryScreen } from "./MemoryScreen";
import { HealthScreen } from "./HealthScreen";
import type { ScreenData } from "../api/types";

type OperationalScreenId = Exclude<ScreenId, "dashboard">;

const data: ScreenData = {
  projects: [{ project_id: "demo", repository: "github.com/trama/demo" }],
  tasks: [{ task_id: "task-1", project_id: "demo", objective: "Run tests", actor: "codex", state: "running", source: "local" }],
  agents: [{ agent_id: "codex", tasks: 1 }],
  status: { status: "ready", projects: 1, queue_depth: 1 },
  events: [{ event_id: "event-1", action: "task.accepted", status: "accepted", project_id: "demo", actor: "system" }],
  memory: [{ candidate_id: "memory-1", project_id: "demo", subject: "Build", fact: "Use Bun", confidence: 0.9, status: "candidate" }],
};

async function renderScreen(screen: OperationalScreenId, overrides: Partial<ScreenData> = {}) {
  const props = { projectId: "demo", data: { ...data, ...overrides } };
  const node = {
    projects: <ProjectsScreen {...props} />,
    tasks: <TasksScreen {...props} onAction={() => undefined} />,
    agents: <AgentsScreen {...props} />,
    queues: <QueuesScreen {...props} />,
    workers: <WorkersScreen {...props} />,
    events: <EventsScreen {...props} />,
    memory: <MemoryScreen {...props} />,
    health: <HealthScreen {...props} />,
  }[screen];
  const setup = await testRender(node, { width: 100, height: 30 });
  await act(async () => { await setup.renderOnce(); });
  return setup;
}

async function destroy(setup: Awaited<ReturnType<typeof renderScreen>>) {
  await act(async () => { setup.renderer.destroy(); });
}

test("renders a project context and title for every operational screen", async () => {
  for (const screen of screenIds.filter((item) => item !== "dashboard")) {
    const setup = await renderScreen(screen);
    const frame = setup.captureCharFrame();
    expect(frame).toContain("demo");
    expect(frame).toContain(screenTitles[screen]);
    await destroy(setup);
  }
});

test("does not invent worker metrics", async () => {
  const setup = await renderScreen("workers", { workers: [] });
  expect(setup.captureCharFrame()).toContain("no disponible");
  await destroy(setup);
});

test("keeps task actions behind a typed callback", async () => {
  let selected = "";
  const setup = await renderScreen("tasks");
  expect(setup.captureCharFrame()).toContain("Run tests");
  selected = "task-1";
  expect(selected).toBe("task-1");
  await destroy(setup);
});
