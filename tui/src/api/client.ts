import type { DashboardData, Overview, Status, Task } from "./types";

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
    return this.getObject<Status>("/v1/status");
  }

  async getOverview(): Promise<Overview> {
    return this.getObject<Overview>("/v1/overview");
  }

  async getTasks(): Promise<Task[]> {
    const payload = await this.getJson("/v1/tasks");
    if (!Array.isArray(payload)) {
      throw new ApiError("Expected an array response", undefined, "/v1/tasks");
    }
    return payload as Task[];
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

  private async getObject<T>(endpoint: string): Promise<T> {
    const payload = await this.getJson(endpoint);
    if (!isObject(payload)) {
      throw new ApiError("Expected an object response", undefined, endpoint);
    }
    return payload as T;
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
