import type { Task } from "../api/types";
import { useKeyboard } from "@opentui/react";
import { Panel } from "../ui/Panel";
import { StatusBadge } from "../ui/StatusBadge";
import { OperationalFrame, type ScreenProps } from "./OperationalFrame";

export type TaskAction = "approve" | "cancel" | "retry";

export function TasksScreen({ projectId, data, selectedId, onSelect, onOpenDetail, onAction }: ScreenProps & { onAction?: (taskId: string, action: TaskAction) => void }) {
  const tasks = data.tasks?.filter((task) => !projectId || !task.project_id || task.project_id === projectId) ?? [];
  useKeyboard((key) => {
    const name = String(key.name).toLowerCase();
    const taskId = selectedId ?? tasks[0]?.task_id;
    if (!taskId) return;
    if (name === "a") onAction?.(taskId, "approve");
    if (name === "x") onAction?.(taskId, "cancel");
    if (name === "y") onAction?.(taskId, "retry");
  });
  return (
    <OperationalFrame title="Tasks" projectId={projectId}>
      <Panel title="Cola de tareas" accent="attention">
        <text fg="#cbd5e1">ESTADO  TAREA                         AGENTE</text>
        {tasks.length === 0 ? <text>no hay tareas</text> : tasks.map((task: Task) => (
          <box key={task.task_id} flexDirection="row" onMouseUp={() => onSelect?.(task.task_id)}>
            <StatusBadge state={task.state ?? "unavailable"} label={`${task.task_id}  ${task.objective ?? "sin objetivo"}`} />
            <text wrapMode="none">{`  ${task.actor ?? "no disponible"}${selectedId === task.task_id ? "  [Enter detalle]" : ""}`}</text>
          </box>
        ))}
        {tasks[0] && <text fg="#7890A5">Enter detalle · a aprobar · x cancelar · y reintentar</text>}
      </Panel>
    </OperationalFrame>
  );
}
