export type Status = {
  status?: string;
  projects?: number;
  queue_depth?: number;
  active_dispatches?: number;
  queue_capacity?: number;
  max_concurrency?: number;
  dispatcher_status?: string;
  results?: number;
};

export type HealthStatus = {
  status: string;
  service: string;
};

export type ProjectManifest = {
  project_id: string;
  organization_id?: string;
  repository: string;
  default_branch?: string;
  capabilities?: string[];
  commands?: Record<string, string>;
  policies?: Record<string, boolean>;
};

export type Phase = {
  phase_id: string;
  name?: string;
  status?: string;
  progress?: number;
  completed_tasks?: number;
  total_tasks?: number;
};

export type Agent = {
  agent_id: string;
  active?: number;
  completed?: number;
  tasks?: number;
  blocked?: number;
};

export type Task = {
  task_id: string;
  objective?: string;
  actor?: string;
  state?: string;
  source?: string;
  project_id?: string;
  organization_id?: string;
  phase_id?: string;
  requirement_id?: string;
  correlation_id?: string;
  approved_by?: string;
  created_at?: string;
};

export type OperationEvent = {
  event_id?: string;
  actor?: string;
  action: string;
  status: string;
  organization_id?: string;
  project_id?: string;
  requirement_id?: string;
  phase_id?: string;
  task_id?: string;
  correlation_id?: string;
  duration_ms?: number;
  details?: Record<string, unknown>;
  created_at?: string;
};

export type TaskLog = {
  log_id?: string;
  created_at?: string;
  level?: string;
  message: string;
  metadata?: Record<string, unknown>;
  organization_id?: string;
  project_id: string;
  requirement_id?: string;
  phase_id?: string;
  task_id?: string;
  actor?: string;
  correlation_id: string;
  duration_ms?: number;
  sequence?: number;
};

export type TimelineEntry = {
  entry_id: string;
  kind: string;
  created_at?: string;
  sequence: number;
  actor: string;
  action?: string;
  status?: string;
  level?: string;
  message?: string;
  metadata?: Record<string, unknown>;
  correlation_id?: string;
  requirement_id?: string;
  phase_id?: string;
  task_id?: string;
};

export type LogQuery = {
  organizationId?: string;
  projectId?: string;
  taskId?: string;
  phaseId?: string;
  requirementId?: string;
  level?: string;
  limit?: number;
};

export type MemoryCandidate = {
  candidate_id: string;
  project_id: string;
  subject: string;
  fact: string;
  confidence?: number;
  status?: string;
  agent_id?: string;
  created_at?: string;
};

export type Worker = {
  worker_id: string;
  status?: string;
  active?: number;
  capacity?: number;
  last_seen_at?: string;
};

export type Overview = {
  phases?: Phase[];
  queue?: Task[];
  agents?: Agent[];
};

export type DashboardData = {
  status: Status;
  phases: Phase[];
  agents: Agent[];
  tasks: Task[];
};

export type ScreenData = {
  projects?: ProjectManifest[];
  tasks?: Task[];
  agents?: Agent[];
  status?: Status;
  health?: HealthStatus;
  events?: OperationEvent[];
  logs?: TaskLog[];
  memory?: MemoryCandidate[];
  workers?: Worker[];
};
