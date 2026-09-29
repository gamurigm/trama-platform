import { useState } from "react";
import { useKeyboard } from "@opentui/react";
import { acceptanceField, criteria, idField, list, useConsole, useLoad } from "../console";
import { statusColor, statusLabel } from "../theme";
import { Action, Detail, Hint, RecordList } from "./Primitives";

export function TasksView() {
  const { client, locked, project, form, inspect, run } = useConsole();
  const [selected, select] = useState(0);
  const loaded = useLoad(async () => {
    const [tasks, projects, requirements, phases] = await Promise.all([client.getTaskEnvelopes(), client.getProjects(), client.getRequirements(), client.getPhases()]);
    return { tasks: tasks.filter((t) => !project || t.project_id === project.project_id), projects, requirements, phases };
  }, [project?.project_id]);
  const data = loaded.data;
  const tasks = data?.tasks ?? [];
  const task = tasks[selected];
  const create = () => form({ title: "Nueva tarea", description: "La tarea quedará por aprobar. Define su alcance y sus resultados esperados.", fields: [
    { name: "project_id", label: "Proyecto", required: true, initial: project?.project_id ?? data?.projects[0]?.project_id,
      hint: data?.projects.map((p) => p.project_id).join(" · ") || "Registra primero un proyecto",
      validate: (v) => data?.projects.some((p) => p.project_id === v) ? undefined : "Proyecto no registrado" },
    idField("task_id", "ID de la tarea"), { name: "objective", label: "Objetivo", multiline: true, required: true },
    { name: "actor", label: "Agente o actor", initial: "codex", required: true },
    { name: "repository", label: "Repositorio", initial: project?.repository, hint: "Vacío = repositorio del proyecto" },
    { name: "branch", label: "Rama", initial: project?.default_branch, hint: "Vacío = rama principal del proyecto" },
    { name: "worktree", label: "Directorio de trabajo (worktree)", required: true, initial: project?.repository },
    { name: "allowed_paths", label: "Rutas permitidas", multiline: true, hint: "Una ruta por línea; limita el alcance de la tarea" },
    { name: "requirement_id", label: "Requisito asociado (opcional)", hint: data?.requirements.map((r) => r.requirement_id).join(" · ") },
    { name: "phase_id", label: "Fase asociada (opcional)", hint: data?.phases.map((p) => p.phase_id).join(" · ") },
    { name: "depends_on", label: "Depende de estas tareas", hint: "IDs separados por comas" },
    { name: "read_only", label: "Solo lectura", initial: "si", required: true, hint: "si / no",
      validate: (v) => ["si", "sí", "no"].includes(v.toLowerCase()) ? undefined : "Escribe si o no" }, acceptanceField,
  ], onSubmit: (v) => {
    const owner = data!.projects.find((p) => p.project_id === v.project_id)!;
    const requirement = data!.requirements.find((r) => r.requirement_id === v.requirement_id);
    return client.submitTask({ task_id: v.task_id!, project_id: owner.project_id, organization_id: owner.organization_id,
      objective: v.objective!, actor: v.actor!, repository: v.repository || owner.repository, branch: v.branch || owner.default_branch,
      worktree: v.worktree!, allowed_paths: criteria(v.allowed_paths!), depends_on: list(v.depends_on!),
      acceptance_criteria: criteria(v.acceptance_criteria!), read_only: v.read_only!.toLowerCase() !== "no",
      state: "planned", source: v.requirement_id ? "requirement" : "manual", requirement_id: v.requirement_id || null,
      phase_id: v.phase_id || null, correlation_id: requirement?.correlation_id ?? crypto.randomUUID() });
  } });
  const transition = (action: "approve" | "cancel" | "retry") => {
    if (!task) return;
    const labels = { approve: "Aprobar", cancel: "Cancelar", retry: "Reintentar" };
    form({ title: `${labels[action]} · ${task.task_id}`, description: action === "approve" ? "Autoriza su entrega al coordinador cuando las dependencias estén listas."
      : action === "cancel" ? "Se solicitará la cancelación de esta tarea." : "Esta acción vuelve a entregar la tarea al coordinador.",
      fields: action === "approve" ? [{ name: "approver", label: "Tu nombre como aprobador", required: true }] : [],
      submitLabel: `Confirmar: ${labels[action].toLowerCase()}`, onSubmit: (v) => action === "approve" ? client.approve("tasks", task.task_id, v.approver!) : client.transitionTask(task.task_id, action) });
  };
  const timeline = () => {
    if (!task) return;
    void run(async () => {
      const [events, logs] = await Promise.all([client.timeline("tasks", task.task_id), client.getLogs({ task_id: task.task_id })]);
      inspect(`Ejecución · ${task.task_id}`, [...events.map((x) => `${x.created_at}  ${x.actor}  ${x.message ?? x.action ?? ""}  ${x.correlation_id ?? ""}`),
        "── LOGS ──", ...logs.map((x) => `${x.created_at}  ${x.level}  ${x.actor}  ${x.message}  ${x.correlation_id}`)]);
    }, "Timeline cargado");
  };
  useKeyboard((key) => {
    if (locked) return;
    if (key.name === "n") create(); if (key.name === "a") transition("approve"); if (key.name === "x") transition("cancel"); if (key.name === "t") transition("retry");
  });
  return <box flexDirection="column" flexGrow={1} gap={1} minHeight={0}>
    <box flexDirection="row" gap={2}><Action label="N Nueva tarea" onPress={create} /><Hint>A Aprobar · X Cancelar · T Reintentar</Hint></box>
    <RecordList title="Tareas" selected={selected} onSelect={select} onOpen={timeline} loading={loaded.loading} error={loaded.error}
      rows={tasks.map((t) => ({ id: t.task_id, name: t.objective, description: `${t.task_id} · ${statusLabel(t.state)} · ${t.actor}` }))}>
      {task && <>
        <text fg={statusColor(task.state)}>● {statusLabel(task.state)}</text>
        <Detail values={[["Objetivo", task.objective], ["ID / proyecto", `${task.task_id} / ${task.project_id}`], ["Agente", task.actor],
          ["Requisito / fase", `${task.requirement_id ?? "—"} / ${task.phase_id ?? "—"}`], ["Repositorio", task.repository], ["Rama", task.branch],
          ["Worktree", task.worktree], ["Rutas permitidas", task.allowed_paths], ["Dependencias", task.depends_on],
          ["Aceptación", task.acceptance_criteria], ["Aprobado por", task.approved_by], ["Correlación", task.correlation_id]]} />
        <Action label="Enter Timeline y logs" onPress={timeline} />
      </>}
    </RecordList>
  </box>;
}
