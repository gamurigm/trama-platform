import type { Task } from "../api/types";
import { TextAttributes } from "@opentui/core";

function stateIcon(state: string | undefined): string {
  const normalized = state?.toLowerCase();
  if (normalized === "running" || normalized === "active" || normalized === "in_progress") return "›";
  if (normalized === "blocked" || normalized === "failed" || normalized === "error") return "!";
  if (normalized === "success" || normalized === "completed" || normalized === "done") return "✓";
  return "○";
}

function textOrId(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

export function TaskTable({ tasks }: { tasks: Task[] }) {
  return (
    <box border borderStyle="single" title="Tareas" titleColor="#facc15" flexDirection="column" padding={1} flexGrow={1}>
      <text attributes={TextAttributes.BOLD} fg="#cbd5e1">{"ESTADO  OBJETIVO                         AGENTE      ORIGEN"}</text>
      {tasks.length === 0 ? (
        <text fg="#94a3b8">sin tareas en cola</text>
      ) : (
        tasks.map((task) => (
          <text key={task.task_id}>
            <span fg={task.state === "blocked" ? "#f87171" : "#86efac"}>{stateIcon(task.state)} </span>
            {textOrId(task.objective, task.task_id).slice(0, 32).padEnd(32, " ")}
            {" "}{textOrId(task.actor, "-").slice(0, 10).padEnd(10, " ")}
            {" "}{textOrId(task.source, "-")}
          </text>
        ))
      )}
    </box>
  );
}
