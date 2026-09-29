export type Status = {
  status?: string;
  projects?: number;
  queue_depth?: number;
  active_dispatches?: number;
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

export type Project = {
  project_id: string; organization_id: string; repository: string; default_branch: string;
  capabilities: string[]; commands: Record<string, string>;
};
export type Requirement = {
  requirement_id: string; organization_id: string; project_id: string; title: string;
  description: string; kind: string; acceptance_criteria: string[]; status: string;
  correlation_id?: string | null;
};
export type ProjectPhase = {
  phase_id: string; requirement_id: string; organization_id: string; project_id: string;
  name: string; sequence: number; depends_on: string[]; acceptance_criteria: string[];
  status: string; approved_by?: string | null; correlation_id?: string | null;
};
export type PlanProposal = {
  proposal_id: string; requirement_id: string; organization_id: string; project_id: string;
  model_profile: string; input_refs: string[]; phase_ids: string[]; task_ids: string[];
  summary: string; status: string; version: number; correlation_id: string; approved_by?: string | null;
};
export type TaskEnvelope = {
  task_id: string; organization_id: string; project_id: string; objective: string; actor: string;
  repository: string; branch: string; worktree: string; allowed_paths: string[]; depends_on: string[];
  acceptance_criteria: string[]; state: string; source: string; read_only: boolean;
  requirement_id?: string | null; phase_id?: string | null; correlation_id?: string | null;
  approved_by?: string | null;
};
export type TimelineEntry = {
  entry_id: string; kind: string; created_at: string; sequence: number; actor: string;
  action?: string | null; status?: string | null; level?: string | null; message?: string | null;
  correlation_id?: string | null;
};
export type TaskLog = {
  log_id: string; created_at: string; level: string; message: string; actor: string;
  project_id: string; correlation_id: string; task_id?: string | null; phase_id?: string | null;
};
export type Setting = {
  name: string; value: string | number | null; active_value: string | number | null;
  source: "default" | "user" | "environment"; read_only: boolean; restart_required: boolean;
};
export type SecretInfo = { name: string; configured: boolean; source?: string; restart_required?: boolean };
export type ConfigSnapshot = { settings: Setting[]; secrets: SecretInfo[]; restart_required: boolean };
export type IntegrationReport = {
  id: string; label: string; status: string; configured: boolean; detail: string;
  checked_at: string; tools: string[];
};
export type IntegrationSnapshot = { integrations: IntegrationReport[]; tools: string[] };
export type LogFilters = Partial<Record<"project_id" | "requirement_id" | "phase_id" | "task_id" | "level", string>>;
