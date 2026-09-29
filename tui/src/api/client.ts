import type { Agent, DashboardData, Overview, Phase, Status, Task } from "./types";
import type { Project, Requirement, ProjectPhase, PlanProposal, TaskEnvelope, TimelineEntry,
  TaskLog, ConfigSnapshot, IntegrationSnapshot, IntegrationReport, SecretInfo, LogFilters } from "./types";

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
  private token: string | undefined;
  private pendingToken: string | null | undefined;

  setToken(token?: string) { this.token = token || undefined; }
  stageToken(token: string | null) { this.pendingToken = token; }
  activateStagedToken() {
    if (this.pendingToken !== undefined) this.setToken(this.pendingToken ?? undefined);
    this.pendingToken = undefined;
  }

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

  private async list<T>(endpoint: string, fields: string[]): Promise<T[]> {
    return collection(await this.getJson(endpoint), "items", endpoint, (value) => {
      for (const field of fields) requiredString(value, field, endpoint);
      return value as T;
    });
  }

  private async entity<T>(endpoint: string, fields: string[], method = "GET", body?: unknown): Promise<T> {
    const payload = await this.getJson(endpoint, method, body);
    if (!isObject(payload)) invalidPayload(endpoint, "Respuesta no válida");
    for (const field of fields) requiredString(payload, field, endpoint);
    return payload as T;
  }

  getProjects() { return this.list<Project>("/v1/projects", ["project_id", "organization_id", "repository", "default_branch"]); }
  registerProject(value: Project) { return this.entity<Project>("/v1/projects", ["project_id"], "POST", value); }
  getRequirements(project?: string) { return this.list<Requirement>(`/v1/requirements${query({ project_id: project })}`, ["requirement_id", "project_id", "title", "description", "status"]); }
  registerRequirement(value: Requirement) { return this.entity<Requirement>("/v1/requirements", ["requirement_id"], "POST", value); }
  getPhases(project?: string) { return this.list<ProjectPhase>(`/v1/phases${query({ project_id: project })}`, ["phase_id", "project_id", "requirement_id", "name", "status"]); }
  registerPhase(value: ProjectPhase) { return this.entity<ProjectPhase>("/v1/phases", ["phase_id"], "POST", value); }
  getPlans() { return this.list<PlanProposal>("/v1/plans", ["proposal_id", "requirement_id", "project_id", "summary", "status", "correlation_id"]); }
  registerPlan(value: PlanProposal) { return this.entity<PlanProposal>("/v1/plans", ["proposal_id"], "POST", value); }
  getTaskEnvelopes() { return this.list<TaskEnvelope>("/v1/tasks", ["task_id", "project_id", "objective", "actor", "state", "repository", "branch", "worktree"]); }
  submitTask(value: TaskEnvelope) { return this.entity<{task_id: string; status: string}>("/v1/tasks", ["task_id", "status"], "POST", value); }
  approve(kind: "tasks" | "phases" | "plans", id: string, approver: string) {
    if (!approver.trim()) throw new Error("Indica quién aprueba esta operación");
    return this.entity(`/v1/${kind}/${encodeURIComponent(id)}/approve`, [], "POST", { approver });
  }
  transitionTask(id: string, action: "cancel" | "retry") { return this.entity<TaskEnvelope>(`/v1/tasks/${encodeURIComponent(id)}/${action}`, ["task_id", "state"], "POST"); }
  timeline(kind: "tasks" | "phases", id: string) { return this.list<TimelineEntry>(`/v1/${kind}/${encodeURIComponent(id)}/timeline`, ["entry_id", "kind", "actor", "created_at"]); }
  getLogs(filters: LogFilters = {}) { return this.list<TaskLog>(`/v1/logs${query(filters)}`, ["log_id", "created_at", "level", "message", "actor", "correlation_id"]); }
  getAgents() { return this.list<Agent>("/v1/agents", ["agent_id"]); }
  async getConfig(): Promise<ConfigSnapshot> {
    const value = await this.getObject("/v1/config");
    if (!Array.isArray(value.settings) || !Array.isArray(value.secrets) || typeof value.restart_required !== "boolean") invalidPayload("/v1/config", "Configuración no válida");
    return value as ConfigSnapshot;
  }
  saveConfig(values: Record<string, string | number | null>) { return this.entity<ConfigSnapshot>("/v1/config", [], "PUT", { values }); }
  getSecrets() { return this.list<SecretInfo>("/v1/config/secrets", ["name"]); }
  setSecret(name: string, value: string) { return this.entity<SecretInfo>(`/v1/config/secrets/${encodeURIComponent(name)}`, ["name"], "PUT", { value }); }
  deleteSecret(name: string) { return this.entity<SecretInfo>(`/v1/config/secrets/${encodeURIComponent(name)}`, ["name"], "DELETE"); }
  async getIntegrations(): Promise<IntegrationSnapshot> {
    const value = await this.getObject("/v1/integrations");
    if (!Array.isArray(value.integrations) || !Array.isArray(value.tools)) invalidPayload("/v1/integrations", "Diagnóstico no válido");
    return value as IntegrationSnapshot;
  }
  checkIntegration(id: string) { return this.entity<IntegrationReport>(`/v1/integrations/${encodeURIComponent(id)}/check`, ["id", "status", "detail"], "POST"); }
  cccc(action: "start" | "stop") { return this.entity<IntegrationReport>(`/v1/integrations/cccc/${action}`, ["id", "status"], "POST"); }
  configureHermes() { return this.entity<IntegrationReport>("/v1/integrations/hermes/configure", ["id", "status"], "POST"); }

  private async getObject(endpoint: string): Promise<Record<string, unknown>> {
    const payload = await this.getJson(endpoint);
    if (!isObject(payload)) {
      throw new ApiError("Expected an object response", undefined, endpoint);
    }
    return payload;
  }

  private async getJson(endpoint: string, method = "GET", body?: unknown): Promise<unknown> {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const response = await this.fetchImpl(`${this.baseUrl}${endpoint}`, {
        signal: controller.signal, method,
        headers: { ...(body === undefined ? {} : { "Content-Type": "application/json" }),
          ...(this.token ? { Authorization: `Bearer ${this.token}` } : {}) },
        ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      });
      if (!response.ok) {
        let detail = "";
        if (!endpoint.includes("/secrets/")) {
          try {
            const error = await response.json() as {detail?: unknown};
            if (typeof error.detail === "string") detail = error.detail;
            else if (Array.isArray(error.detail)) detail = error.detail.map((item) => `${item.loc?.slice(1).join(".")}: ${item.msg}`).join(" · ");
          } catch {}
        }
        throw new ApiError(detail || `API request failed with status ${response.status}`, response.status, endpoint);
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

function query(values: Record<string, string | undefined>): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(values)) if (value) params.set(key, value);
  return params.size ? `?${params}` : "";
}
