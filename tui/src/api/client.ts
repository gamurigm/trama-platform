import type { Agent, DashboardData, Overview, Phase, Status, Task } from "./types";

const DEFAULT_TIMEOUT_MS = 10_000;

export class ApiError extends Error {
  constructor(
    message: string,
    public readonly status: number | undefined,
    public readonly endpoint: string,
    options?: ErrorOptions,
  ) {
    super(message, options);
    this.name = "ApiError";
  }
}

function isObject(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function invalidPayload(endpoint: string, message: string): never {
  throw new ApiError(message, undefined, endpoint);
}

function requiredString(value: Record<string, unknown>, field: string, endpoint: string): void {
  if (typeof value[field] !== "string") {
    invalidPayload(endpoint, `Expected ${field} to be a string`);
  }
}

function optionalString(value: Record<string, unknown>, field: string, endpoint: string): void {
  if (field in value && typeof value[field] !== "string") {
    invalidPayload(endpoint, `Expected ${field} to be a string`);
  }
}

function optionalNumber(value: Record<string, unknown>, field: string, endpoint: string): void {
  if (field in value && typeof value[field] !== "number") {
    invalidPayload(endpoint, `Expected ${field} to be a number`);
  }
}

function collection<T>(
  value: unknown,
  field: string,
  endpoint: string,
  validateEntry: (entry: Record<string, unknown>, endpoint: string) => T,
): T[] {
  if (!Array.isArray(value)) {
    invalidPayload(endpoint, `Expected ${field} to be an array`);
  }
  return value.map((entry) => {
    if (!isObject(entry)) {
      invalidPayload(endpoint, `Expected every ${field} entry to be an object`);
    }
    return validateEntry(entry, endpoint);
  });
}

function phase(value: Record<string, unknown>, endpoint: string): Phase {
  requiredString(value, "phase_id", endpoint);
  optionalString(value, "name", endpoint);
  optionalString(value, "status", endpoint);
  optionalNumber(value, "progress", endpoint);
  optionalNumber(value, "completed_tasks", endpoint);
  optionalNumber(value, "total_tasks", endpoint);
  return value as Phase;
}

function agent(value: Record<string, unknown>, endpoint: string): Agent {
  requiredString(value, "agent_id", endpoint);
  optionalNumber(value, "active", endpoint);
  optionalNumber(value, "completed", endpoint);
  optionalNumber(value, "tasks", endpoint);
  optionalNumber(value, "blocked", endpoint);
  return value as Agent;
}

function task(value: Record<string, unknown>, endpoint: string): Task {
  requiredString(value, "task_id", endpoint);
  optionalString(value, "objective", endpoint);
  optionalString(value, "actor", endpoint);
  optionalString(value, "state", endpoint);
  optionalString(value, "source", endpoint);
  return value as Task;
}

function status(value: Record<string, unknown>, endpoint: string): Status {
  optionalString(value, "status", endpoint);
  optionalNumber(value, "projects", endpoint);
  optionalNumber(value, "queue_depth", endpoint);
  optionalNumber(value, "active_dispatches", endpoint);
  return value as Status;
}

function overview(value: Record<string, unknown>, endpoint: string): Overview {
  return {
    ...value,
    phases: "phases" in value ? collection(value.phases, "phases", endpoint, phase) : undefined,
    queue: "queue" in value ? collection(value.queue, "queue", endpoint, task) : undefined,
    agents: "agents" in value ? collection(value.agents, "agents", endpoint, agent) : undefined,
  };
}

export class TramaApiClient {
  private readonly baseUrl: string;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;

  constructor(baseUrl: string, fetchImpl: typeof fetch = fetch, timeoutMs = DEFAULT_TIMEOUT_MS) {
    this.baseUrl = baseUrl.replace(/\/+$/, "");
    this.fetchImpl = fetchImpl;
    this.timeoutMs = timeoutMs;
  }

  async getStatus(): Promise<Status> {
    return status(await this.getObject("/v1/status"), "/v1/status");
  }

  async getOverview(): Promise<Overview> {
    return overview(await this.getObject("/v1/overview"), "/v1/overview");
  }

  async getTasks(): Promise<Task[]> {
    const payload = await this.getJson("/v1/tasks");
    return collection(payload, "tasks", "/v1/tasks", task);
  }

  async getDashboard(): Promise<DashboardData> {
    const [status, overview] = await Promise.all([this.getStatus(), this.getOverview()]);
    const tasks = Array.isArray(overview.queue) ? overview.queue : await this.getTasks();
    return {
      status,
      phases: Array.isArray(overview.phases) ? overview.phases : [],
      agents: Array.isArray(overview.agents) ? overview.agents : [],
      tasks,
    };
  }

  private async getObject(endpoint: string): Promise<Record<string, unknown>> {
    const payload = await this.getJson(endpoint);
    if (!isObject(payload)) {
      throw new ApiError("Expected an object response", undefined, endpoint);
    }
    return payload;
  }

  private async getJson(endpoint: string): Promise<unknown> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetchImpl(`${this.baseUrl}${endpoint}`, { signal: controller.signal });
      if (!response.ok) {
        throw new ApiError(`API request failed with status ${response.status}`, response.status, endpoint);
      }
      try {
        return await response.json();
      } catch (error) {
        throw new ApiError("API returned invalid JSON", response.status, endpoint, {
          cause: error,
        });
      }
    } catch (error) {
      if (error instanceof ApiError) {
        throw error;
      }
      throw new ApiError("API request failed", undefined, endpoint, { cause: error });
    } finally {
      clearTimeout(timeout);
    }
  }
}
