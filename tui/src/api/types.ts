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
