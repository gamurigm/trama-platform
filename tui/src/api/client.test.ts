import { expect, test } from "bun:test";
import { ApiError, TramaApiClient } from "./client";
import type { DashboardData, Overview, Status, Task } from "./types";

const baseUrl = "http://127.0.0.1:8090";
const status: Status = { status: "ok", projects: 2, queue_depth: 1, active_dispatches: 1 };
const tasks: Task[] = [{ task_id: "task-1", objective: "Ship TUI", state: "running" }];
const fixtures = {
  status,
  overview: {
    phases: [{ phase_id: "phase-1", name: "Build", progress: 50 }],
    queue: tasks,
    agents: [{ agent_id: "agent-1", active: 1 }],
  },
};

function fakeFetch(fixturesByEndpoint: Record<string, unknown>, calls: Request[] = []): typeof fetch {
  return (async (input, init) => {
    const request = new Request(input, init);
    calls.push(request);
    const endpoint = new URL(request.url).pathname;
    if (!(endpoint.slice("/v1/".length) in fixturesByEndpoint)) {
      return new Response("not found", { status: 404 });
    }
    return Response.json(fixturesByEndpoint[endpoint.slice("/v1/".length)]);
  }) as typeof fetch;
}

test("combines status, overview, and agents", async () => {
  const calls: Request[] = [];
  const client = new TramaApiClient(baseUrl, fakeFetch(fixtures, calls));

  const expectedDashboard: DashboardData = {
    status,
    phases: fixtures.overview.phases,
    agents: fixtures.overview.agents,
    tasks,
  };

  await expect(client.getDashboard()).resolves.toEqual(expectedDashboard);
  expect(calls.map((request) => new URL(request.url).pathname)).toEqual(["/v1/status", "/v1/overview"]);
  expect(calls.every((request) => request.signal instanceof AbortSignal)).toBe(true);
});

test("falls back to /v1/tasks when overview has no queue", async () => {
  const calls: Request[] = [];
  const overviewWithoutQueue: Overview = { phases: [], agents: [] };
  const client = new TramaApiClient(baseUrl, fakeFetch({ overview: overviewWithoutQueue, status, tasks }, calls));

  await expect(client.getDashboard()).resolves.toMatchObject({ tasks });
  expect(calls.map((request) => new URL(request.url).pathname)).toEqual([
    "/v1/status",
    "/v1/overview",
    "/v1/tasks",
  ]);
});

test("converts non-2xx responses to ApiError", async () => {
  const fetchError = (async () => new Response("unavailable", { status: 503 })) as typeof fetch;
  const client = new TramaApiClient(baseUrl, fetchError);

  await expect(client.getStatus()).rejects.toBeInstanceOf(ApiError);
  await expect(client.getStatus()).rejects.toMatchObject({ status: 503, endpoint: "/v1/status" });
});

test("rejects invalid JSON and non-object payloads", async () => {
  const invalidJson = (async () => new Response("not-json", { status: 200 })) as typeof fetch;
  await expect(new TramaApiClient(baseUrl, invalidJson).getStatus()).rejects.toBeInstanceOf(ApiError);

  const arrayPayload = (async () => Response.json([])) as typeof fetch;
  await expect(new TramaApiClient(baseUrl, arrayPayload).getStatus()).rejects.toBeInstanceOf(ApiError);
});

test("aborts a request when it exceeds the timeout", async () => {
  let receivedSignal: AbortSignal | undefined;
  const hangingFetch = (async (_input, init) => {
    receivedSignal = init?.signal as AbortSignal;
    await new Promise<void>((resolve) => receivedSignal?.addEventListener("abort", () => resolve()));
    throw new DOMException("The operation was aborted", "AbortError");
  }) as typeof fetch;

  await expect(new TramaApiClient(baseUrl, hangingFetch, 1).getStatus()).rejects.toBeInstanceOf(ApiError);
  expect(receivedSignal?.aborted).toBe(true);
});
