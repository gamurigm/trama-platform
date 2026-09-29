import { useState } from "react";
import { useKeyboard } from "@opentui/react";
import { acceptanceField, criteria, idField, list, useConsole, useLoad } from "../console";
import { clean, statusColor, statusLabel, theme } from "../theme";
import { Action, Detail, Hint, RecordList } from "./Primitives";

export function PlanningView() {
  const { client, locked, project, form, inspect, run } = useConsole();
  const [mode, setMode] = useState<"requirements" | "phases" | "plans">("requirements");
  const [selected, select] = useState(0);
  const loaded = useLoad(async () => {
    const [requirements, phases, plans, projects] = await Promise.all([client.getRequirements(project?.project_id), client.getPhases(project?.project_id), client.getPlans(), client.getProjects()]);
    return { requirements, phases, plans: plans.filter((p) => !project || p.project_id === project.project_id), projects };
  }, [project?.project_id]);
  const data = loaded.data;
  const requirements = data?.requirements ?? [];
  const phases = data?.phases ?? [];
  const plans = data?.plans ?? [];
  const rows = mode === "requirements" ? requirements.map((x) => ({ id: x.requirement_id, name: x.title, description: `${x.requirement_id} · ${statusLabel(x.status)}` }))
    : mode === "phases" ? phases.map((x) => ({ id: x.phase_id, name: `${x.sequence}. ${x.name}`, description: `${x.phase_id} · ${statusLabel(x.status)}` }))
    : plans.map((x) => ({ id: x.proposal_id, name: x.proposal_id, description: `${statusLabel(x.status)} · ${x.summary}` }));
  const current = mode === "requirements" ? requirements[selected] : mode === "phases" ? phases[selected] : plans[selected];
  const change = (next: typeof mode) => { setMode(next); select(0); };
  const projectField = { name: "project_id", label: "Proyecto", initial: project?.project_id ?? data?.projects[0]?.project_id, required: true,
    hint: (data?.projects ?? []).map((p) => p.project_id).join(" · ") || "Registra primero un proyecto en la vista 2",
    validate: (value: string) => data?.projects.some((p) => p.project_id === value) ? undefined : "Selecciona un ID de proyecto registrado" };
  const requirementField = { ...idField("requirement_id", "Requisito"), initial: requirements[0]?.requirement_id,
    hint: requirements.map((r) => `${r.requirement_id}: ${r.title}`).join(" · ") || "Crea primero un requisito (N)" };
  const owner = (id: string) => data?.projects.find((p) => p.project_id === id)?.organization_id ?? "default";
  const newRequirement = () => form({ title: "Nuevo requisito", description: "Describe qué necesita el proyecto y cómo se comprobará.", fields: [
    projectField, idField("requirement_id", "ID del requisito"), { name: "title", label: "Título", required: true },
    { name: "description", label: "Descripción", required: true, multiline: true },
    { name: "kind", label: "Tipo", initial: "feature", hint: "feature · change · module · refactor · bugfix", required: true,
      validate: (v) => ["feature", "change", "module", "refactor", "bugfix"].includes(v) ? undefined : "Elige uno de los tipos indicados" }, acceptanceField,
  ], onSubmit: (v) => client.registerRequirement({ requirement_id: v.requirement_id!, project_id: v.project_id!, organization_id: owner(v.project_id!), title: v.title!,
    description: v.description!, kind: v.kind!, acceptance_criteria: criteria(v.acceptance_criteria!), status: "proposed", correlation_id: crypto.randomUUID() }) });
  const newPhase = () => form({ title: "Nueva fase", description: "Sin dependencias, una fase puede ejecutarse en paralelo tras su aprobación.", fields: [
    projectField, requirementField, idField("phase_id", "ID de la fase"), { name: "name", label: "Nombre de la fase", required: true },
    { name: "sequence", label: "Orden", initial: String(phases.length + 1), required: true,
      validate: (v) => /^\d+$/.test(v) && +v >= 1 && +v <= 1000 ? undefined : "Introduce un entero de 1 a 1000" },
    { name: "depends_on", label: "Depende de estas fases", hint: "IDs separados por comas. Vacío = puede avanzar en paralelo." }, acceptanceField,
  ], onSubmit: (v) => client.registerPhase({ phase_id: v.phase_id!, requirement_id: v.requirement_id!, project_id: v.project_id!, organization_id: owner(v.project_id!),
    name: v.name!, sequence: +v.sequence!, depends_on: list(v.depends_on!), acceptance_criteria: criteria(v.acceptance_criteria!), status: "planned",
    correlation_id: requirements.find((r) => r.requirement_id === v.requirement_id)?.correlation_id }) });
  const newPlan = () => form({ title: "Propuesta de plan", description: "Agrupa fases y tareas existentes. Se registra como propuesta pendiente de aprobación.", fields: [
    projectField, requirementField, idField("proposal_id", "ID de propuesta"), { name: "summary", label: "Resumen del plan", multiline: true, required: true },
    { name: "phase_ids", label: "Fases del plan", hint: phases.map((p) => p.phase_id).join(", ") || "IDs separados por comas" },
    { name: "task_ids", label: "Tareas del plan", hint: "IDs de tareas ya registradas, separados por comas" },
    { name: "model_profile", label: "Origen o perfil de la propuesta", initial: "manual", required: true, hint: "manual para una propuesta escrita por ti; no ejecuta un modelo" },
    { name: "input_refs", label: "Referencias de entrada", multiline: true, hint: "Una referencia por línea (opcional)" },
  ], onSubmit: (v) => client.registerPlan({ proposal_id: v.proposal_id!, requirement_id: v.requirement_id!, project_id: v.project_id!, organization_id: owner(v.project_id!),
    summary: v.summary!, phase_ids: list(v.phase_ids!), task_ids: list(v.task_ids!), model_profile: v.model_profile!, input_refs: criteria(v.input_refs!),
    status: "proposed", version: 1, correlation_id: requirements.find((r) => r.requirement_id === v.requirement_id)?.correlation_id ?? crypto.randomUUID() }) });
  const approve = () => {
    if (mode === "requirements" || !current || !rows[selected]) return;
    const id = rows[selected]!.id;
    form({ title: `Aprobar ${id}`, description: "Esta aprobación habilita las fases y tareas del plan para su ejecución cuando sus dependencias estén listas.",
      fields: [{ name: "approver", label: "Tu nombre como aprobador", required: true }], submitLabel: "Aprobar explícitamente",
      onSubmit: (v) => client.approve(mode, id, v.approver!) });
  };
  const timeline = () => {
    const phase = phases[selected];
    if (mode === "phases" && phase) void run(async () => { const items = await client.timeline("phases", phase.phase_id);
      inspect(`Timeline · ${phase.phase_id}`, items.map((x) => `${x.created_at}  ${x.actor}  ${x.message ?? x.action ?? ""}  ${x.correlation_id ?? ""}`)); }, "Timeline cargado");
  };
  useKeyboard((key) => {
    if (locked) return;
    if (key.name === "n") newRequirement(); if (key.name === "f") newPhase(); if (key.name === "p") newPlan(); if (key.name === "a") approve();
    if (key.name === "tab") { key.preventDefault(); change(mode === "requirements" ? "phases" : mode === "phases" ? "plans" : "requirements"); }
  });
  return <box flexDirection="column" flexGrow={1} gap={1} minHeight={0}>
    <box flexDirection="row" gap={1} flexWrap="wrap">
      <Action label={`${mode === "requirements" ? "● " : ""}Requisitos`} onPress={() => change("requirements")} />
      <Action label={`${mode === "phases" ? "● " : ""}Fases`} onPress={() => change("phases")} />
      <Action label={`${mode === "plans" ? "● " : ""}Planes`} onPress={() => change("plans")} />
    </box>
    <Hint>N Requisito · F Fase · P Plan · A Aprobar · Tab Cambiar lista</Hint>
    <RecordList title={mode === "requirements" ? "Requisitos" : mode === "phases" ? "Fases" : "Planes"} rows={rows} selected={selected} onSelect={select}
      onOpen={timeline} loading={loaded.loading} error={loaded.error}>
      {current && <>
        <text fg={statusColor(current.status)}>● {statusLabel(current.status)}</text>
        <Detail values={[["ID", rows[selected]?.id], ["Proyecto", current.project_id],
          ...("title" in current ? [["Título", current.title], ["Descripción", current.description], ["Aceptación", current.acceptance_criteria]] as [string, unknown][] : []),
          ...("sequence" in current ? [["Nombre", current.name], ["Dependencias", current.depends_on.length ? current.depends_on : "Sin dependencias · paralela"], ["Aceptación", current.acceptance_criteria]] as [string, unknown][] : []),
          ...("summary" in current ? [["Resumen", current.summary], ["Fases", current.phase_ids], ["Tareas", current.task_ids]] as [string, unknown][] : []),
          ["Correlación", current.correlation_id], ...("approved_by" in current ? [["Aprobado por", current.approved_by]] as [string, unknown][] : [])]} />
        {mode !== "requirements" && <Action label="A Aprobar" onPress={approve} />}
        {mode === "phases" && <Action label="Enter Ver timeline" onPress={timeline} />}
      </>}
    </RecordList>
  </box>;
}
