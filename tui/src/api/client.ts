import type {
  Agent,
  DashboardData,
  HealthStatus,
  LogQuery,
  OperationEvent,
  Overview,
  Phase,
  ProjectManifest,
  Status,
  Task,
  TaskLog,
  TimelineEntry,
} from "./types";

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
  optionalNumber(value, "queue_capacity", endpoint);
  optionalNumber(value, "max_concurrency", endpoint);
  optionalString(value, "dispatcher_status", endpoint);
  optionalNumber(value, "results", endpoint);
  return value as Status;
}

function health(value: Record<string, unknown>, endpoint: string): HealthStatus {
  requiredString(value, "status", endpoint);
  requiredString(value, "service", endpoint);
  return value as HealthStatus;
}

function project(value: Record<string, unknown>, endpoint: string): ProjectManifest {
  requiredString(value, "project_id", endpoint);
  requiredString(value, "repository", endpoint);
  optionalString(value, "organization_id", endpoint);
  optionalString(value, "default_branch", endpoint);
  return value as ProjectManifest;
}

function event(value: Record<string, unknown>, endpoint: string): OperationEvent {
  requiredString(value, "action", endpoint);
  requiredString(value, "status", endpoint);
  optionalString(value, "event_id", endpoint);
  optionalString(value, "actor", endpoint);
  optionalString(value, "project_id", endpoint);
  optionalString(value, "task_id", endpoint);
  optionalString(value, "created_at", endpoint);
  return value as OperationEvent;
}

function log(value: Record<string, unknown>, endpoint: string): TaskLog {
  requiredString(value, "message", endpoint);
  requiredString(value, "project_id", endpoint);
  requiredString(value, "correlation_id", endpoint);
  optionalString(value, "log_id", endpoint);
  optionalString(value, "created_at", endpoint);
  optionalString(value, "level", endpoint);
  optionalString(value, "task_id", endpoint);
  return value as TaskLog;
}

function timeline(value: Record<string, unknown>, endpoint: string): TimelineEntry {
  requiredString(value, "entry_id", endpoint);
  requiredString(value, "kind", endpoint);
  requiredNumber(value, "sequence", endpoint);
  requiredString(value, "actor", endpoint);
  optionalString(value, "created_at", endpoint);
  optionalString(value, "action", endpoint);
  optionalString(value, "status", endpoint);
  optionalString(value, "message", endpoint);
  optionalString(value, "task_id", endpoint);
  return value as TimelineEntry;
}

function requiredNumber(value: Record<string, unknown>, field: string, endpoint: string): void {
  if (typeof value[field] !== "number") {
    invalidPayload(endpoint, `Expected ${field} to be a number`);
  }
}

function boundedLimit(limit: number | undefined): number {
  return Math.max(1, Math.min(1000, Math.trunc(limit ?? 100)));
}

function addQuery(endpoint: string, entries: Array<[string, string | number | undefined]>): string {
  const query = new URLSearchParams();
  for (const [key, value] of entries) {
    if (value !== undefined) query.set(key, String(value));
  }
  const encoded = query.toString();
  return encoded ? `${endpoint}?${encoded}` : endpoint;
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

  async getOverview(projectId?: string): Promise<Overview> {
    const endpoint = addQuery("/v1/overview", [["project_id", projectId]]);
    return overview(await this.getObject(endpoint), "/v1/overview");
  }

  async listProjects(): Promise<ProjectManifest[]> {
    const endpoint = "/v1/projects";
    return collection(await this.getJson(endpoint), "projects", endpoint, project);
  }

  async getHealth(): Promise<HealthStatus> {
    const endpoint = "/health";
    return health(await this.getObject(endpoint), endpoint);
  }

  async listEvents(limit = 100): Promise<OperationEvent[]> {
    const endpoint = addQuery("/v1/events", [["limit", boundedLimit(limit)]]);
    return collection(await this.getJson(endpoint), "events", "/v1/events", event);
  }

  async listLogs(params: LogQuery = {}): Promise<TaskLog[]> {
    const endpoint = addQuery("/v1/logs", [
      ["organization_id", params.organizationId],
      ["project_id", params.projectId],
      ["task_id", params.taskId],
      ["phase_id", params.phaseId],
      ["requirement_id", params.requirementId],
      ["level", params.level],
      ["limit", boundedLimit(params.limit)],
    ]);
    return collection(await this.getJson(endpoint), "logs", "/v1/logs", log);
  }

  async getTaskTimeline(taskId: string, limit = 100): Promise<TimelineEntry[]> {
    const endpoint = addQuery(`/v1/tasks/${encodeURIComponent(taskId)}/timeline`, [["limit", boundedLimit(limit)]]);
    return collection(await this.getJson(endpoint), "timeline", "/v1/tasks/:taskId/timeline", timeline);
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
