import type { Task } from "../api/types";
import { Panel } from "../ui/Panel";
import { StatusBadge } from "../ui/StatusBadge";

export function ActivityPanel({ tasks }: { tasks: Task[] }) {
  const recent = tasks.slice(0, 3);
  return (
    <Panel title="Actividad reciente" accent="cognitive" flexGrow={1}>
      {recent.length === 0 ? (
        <text fg="#7890A5">sin actividad reciente</text>
      ) : (
        recent.map((task) => (
          <StatusBadge key={task.task_id} state={task.state ?? "unavailable"} label={`${task.task_id} · ${task.objective ?? "sin objetivo"}`} />
        ))
      )}
    </Panel>
  );
}
