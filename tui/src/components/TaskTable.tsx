import type { Task } from "../api/types";
import { TextAttributes } from "@opentui/core";
import { Fragment } from "react";

function stateIcon(state: string | undefined): string {
  const normalized = state?.toLowerCase();
  if (normalized === "running" || normalized === "active" || normalized === "in_progress") return "›";
  if (normalized === "blocked" || normalized === "failed" || normalized === "error") return "!";
  if (normalized === "success" || normalized === "succeeded" || normalized === "completed" || normalized === "done") return "✓";
  return "○";
}

function isBlocked(state: string | undefined): boolean {
  return state?.toLowerCase() === "blocked";
}

function textOrId(value: unknown, fallback: string): string {
  return typeof value === "string" && value.trim() ? value : fallback;
}

export function TaskTable({ tasks, compact = false }: { tasks: Task[]; compact?: boolean }) {
  if (compact) {
    return (
      <box flexDirection="column" padding={0} flexGrow={0} height={tasks.length === 0 ? 4 : tasks.length * 2 + 3}>
        <text fg="#facc15">Tareas</text>
        <text attributes={TextAttributes.BOLD} fg="#cbd5e1" wrapMode="none">{"ESTADO  OBJETIVO"}</text>
        <text attributes={TextAttributes.BOLD} fg="#cbd5e1" wrapMode="none">{"AGENTE  ORIGEN"}</text>
        {tasks.length === 0 ? (
          <text fg="#94a3b8">sin tareas en cola</text>
        ) : (
          tasks.map((task) => (
            <Fragment key={task.task_id}>
              <text wrapMode="none" fg={isBlocked(task.state) ? "#f87171" : "#86efac"}>{`${stateIcon(task.state)} ${textOrId(task.objective, task.task_id).slice(0, 32)}`}</text>
              <text wrapMode="none">{`AGENTE ${textOrId(task.actor, "-")}  ORIGEN ${textOrId(task.source, "-")}`}</text>
            </Fragment>
          ))
        )}
      </box>
    );
  }

  return (
    <box border borderStyle="single" title="Tareas" titleColor="#facc15" flexDirection="column" padding={1} flexGrow={1}>
      {compact ? (
        <>
          <text attributes={TextAttributes.BOLD} fg="#cbd5e1" wrapMode="none">{"ESTADO  OBJETIVO"}</text>
          <text attributes={TextAttributes.BOLD} fg="#cbd5e1" wrapMode="none">{"AGENTE  ORIGEN"}</text>
        </>
      ) : (
        <text attributes={TextAttributes.BOLD} fg="#cbd5e1" wrapMode="none">{"ESTADO  OBJETIVO          AGENTE   ORIGEN"}</text>
      )}
      {tasks.length === 0 ? (
        <text fg="#94a3b8">sin tareas en cola</text>
      ) : (
        tasks.map((task) => (
          <Fragment key={task.task_id}>
            <text key={`${task.task_id}-summary`} wrapMode="none">
              <span fg={isBlocked(task.state) ? "#f87171" : "#86efac"}>{stateIcon(task.state)} </span>
              {compact ? textOrId(task.objective, task.task_id).slice(0, 32) : textOrId(task.objective, task.task_id).slice(0, 18).padEnd(18, " ")}
              {!compact && <>{" "}{textOrId(task.actor, "-").slice(0, 8).padEnd(8, " ")}{" "}{textOrId(task.source, "-").slice(0, 6).padEnd(6, " ")}</>}
            </text>
            {compact && <text key={`${task.task_id}-context`} wrapMode="none">{`AGENTE ${textOrId(task.actor, "-")}  ORIGEN ${textOrId(task.source, "-")}`}</text>}
          </Fragment>
        ))
      )}
    </box>
  );
}
