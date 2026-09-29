import { useCallback, useEffect, useRef, useState } from "react";
import { useKeyboard, useRenderer, useTerminalDimensions } from "@opentui/react";
import type { DashboardData, Project } from "./api/types";
import type { TramaApiClient } from "./api/client";
import { ConsoleContext } from "./console";
import type { FormSpec } from "./console";
import { clean, statusColor, statusLabel, theme } from "./theme";
import { Action, Hint, Panel } from "./components/Primitives";
import { FormFields } from "./components/FormFields";
import { ProjectsView } from "./components/ProjectsView";
import { PlanningView } from "./components/PlanningView";
import { TasksView } from "./components/TasksView";
import { ObservabilityView } from "./components/ObservabilityView";
import { IntegrationsView } from "./components/IntegrationsView";
import { detectedRepository, findDetectedProject } from "./repository";

const views = ["Resumen", "Proyectos", "Planificación", "Tareas", "Actividad", "Integraciones"];

export function App({ client, pollMs = 5000 }: { client: TramaApiClient; pollMs?: number }) {
  const renderer = useRenderer();
  const { width } = useTerminalDimensions();
  const [view, setView] = useState(0);
  const [version, setVersion] = useState(0);
  const [project, setProject] = useState<Project>();
  const [data, setData] = useState<DashboardData>();
  const [loadError, setLoadError] = useState("");
  const [form, setForm] = useState<FormSpec>();
  const [detail, setDetail] = useState<{title: string; rows: string[]}>();
  const [notice, setNotice] = useState<{message: string; error?: boolean}>();
  const [busy, setBusy] = useState(false);
  const inFlight = useRef(false);
  const operation = useRef(false);
  const locked = Boolean(form || detail || busy);
  const refreshDashboard = useCallback(async () => {
    if (inFlight.current) return;
    inFlight.current = true;
    try { setData(await client.getDashboard()); setLoadError(""); }
    catch (error) { setLoadError(error instanceof Error ? error.message : "No se pudo conectar"); }
    finally { inFlight.current = false; }
  }, [client]);
  const refresh = () => { setVersion((v) => v + 1); void refreshDashboard(); };
  useEffect(() => {
    void refreshDashboard();
    const timer = setInterval(() => void refreshDashboard(), pollMs);
    return () => clearInterval(timer);
  }, [refreshDashboard, pollMs]);
  useEffect(() => {
    if (!detectedRepository.root) return;
    let alive = true;
    void client.getProjects().then((projects) => {
      const match = findDetectedProject(projects);
      if (alive && match) setProject(match);
    }).catch(() => {});
    return () => { alive = false; };
  }, [client]);
  useEffect(() => { if (!notice) return; const timer = setTimeout(() => setNotice(undefined), 12000); return () => clearTimeout(timer); }, [notice]);
  const run = async (fn: () => Promise<unknown>, success: string) => {
    if (operation.current) return;
    operation.current = true; setBusy(true);
    try { await fn(); setNotice({ message: success }); refresh(); }
    catch (error) { setNotice({ message: error instanceof Error ? error.message : "No se pudo completar", error: true }); }
    finally { operation.current = false; setBusy(false); }
  };
  const activateProject = useCallback((value: Project) => {
    setProject(value);
    setNotice({ message: `Proyecto activo: ${value.project_id}` });
  }, []);
  useKeyboard((key) => {
    if (form) return;
    if (detail) { if (key.name === "escape") { key.preventDefault(); setDetail(undefined); } return; }
    if (busy) return;
    if (/^[1-6]$/.test(key.name)) { key.preventDefault(); setView(+key.name - 1); }
    if (key.name === "r") refresh();
    if (key.name === "q") renderer.destroy();
  });
  return <ConsoleContext.Provider value={{ client, version, locked, project, setProject: activateProject,
    form: (spec) => { if (!operation.current) setForm(spec); }, inspect: (title, rows) => setDetail({ title, rows }), run, refresh }}>
    <box width="100%" height="100%" flexDirection="column" backgroundColor={theme.bg} paddingX={1}>
      <box flexDirection="row" justifyContent="space-between" paddingY={0} flexShrink={0}>
        <text fg={theme.text}><b><span fg={theme.cyan}>▰ </span>TRAMA</b><span fg={theme.muted}>{width >= 70 ? "  /  CENTRO DE OPERACIONES" : ""}</span></text>
        <text fg={loadError ? theme.coral : data ? theme.green : theme.amber}>{loadError ? "● Sin conexión" : data ? "● API activa" : "◌ Conectando..."}</text>
      </box>
      <box flexDirection="row" columnGap={1} rowGap={0} flexWrap="wrap" flexShrink={0}>
        {views.map((label, i) => <box key={label} paddingX={1} backgroundColor={view === i ? theme.selected : theme.bg}
          onMouseDown={() => { if (!locked) setView(i); }}>
          <text fg={view === i ? theme.violet : theme.muted}>{i + 1} {width < 100 && i === 2 ? "Planes" : width < 100 && i === 5 ? "Conexiones" : label}</text>
        </box>)}
      </box>
      <box marginTop={1} marginBottom={1} flexDirection="row" justifyContent="space-between" flexShrink={0}>
        <text fg={theme.violet}>{views[view]} <span fg={theme.muted}>/ {clean(project?.project_id ?? "Todos los proyectos")}</span></text>
        {busy && <text fg={theme.cyan}>◌ Procesando…</text>}
      </box>
      <box flexGrow={1} minHeight={0} position="relative">
        <box position="absolute" top={0} left={0} width="100%" height="100%" visible={!form && !detail}>
          {view === 0 ? <Overview data={data} error={loadError} onNavigate={setView} />
            : view === 1 ? <ProjectsView /> : view === 2 ? <PlanningView /> : view === 3 ? <TasksView />
            : view === 4 ? <ObservabilityView /> : <IntegrationsView />}
        </box>
        <box position="absolute" top={0} left={0} width="100%" height="100%" visible={Boolean(form)} zIndex={2}>
          {form && <FormFields spec={form} onClose={() => setForm(undefined)} onSuccess={() => { setForm(undefined); setNotice({ message: "Operación guardada" }); refresh(); }} />}
        </box>
        <box position="absolute" top={0} left={0} width="100%" height="100%" visible={Boolean(detail)} zIndex={2}>
          {detail && <Panel title={detail.title}><scrollbox focused flexGrow={1} minHeight={0} paddingY={1}>
              {detail.rows.length ? detail.rows.map((row, i) => <text key={i} fg={i % 2 ? theme.muted : theme.text}>{clean(row)}</text>) : <Hint>Todavía no hay eventos para este elemento.</Hint>}
            </scrollbox><Hint>Esc Volver · ↑ ↓ Desplazar</Hint></Panel>
          }
        </box>
      </box>
      <box flexDirection="column" flexShrink={0} marginTop={1}>
        {notice && <text fg={notice.error ? theme.coral : theme.green}>{clean(notice.message)}</text>}
        <text fg={theme.muted}>{form ? "Tab Siguiente · Shift+Tab Atrás · Esc Cancelar" : detail ? "Esc Volver" : "1–6 Vistas · ↑ ↓ Seleccionar · R Actualizar · Q Salir"}</text>
      </box>
    </box>
  </ConsoleContext.Provider>;
}

function Overview({ data, error, onNavigate }: { data?: DashboardData; error: string; onNavigate: (view: number) => void }) {
  const { width } = useTerminalDimensions();
  if (!data) return <Panel title="Bienvenido a TRAMA"><box padding={2} flexDirection="column" gap={1}>
    <text fg={theme.text}>{error ? `API no disponible: ${clean(error)}` : "Conectando..."}</text>
    <Hint>{error ? "R para reintentar. Comprueba el servicio con trama doctor." : "Preparando proyectos, fases y cola de trabajo."}</Hint>
  </box></Panel>;
  const pending = data.tasks.filter((t) => t.state === "planned").length;
  const blocked = data.tasks.filter((t) => t.state === "blocked").length;
  return <scrollbox focused flexGrow={1} minHeight={0}>
    <box flexDirection="column" gap={1}>
      {error && <text fg={theme.coral}>API no disponible · datos anteriores · R reintenta</text>}
      <box flexDirection="row" gap={1}>
        {[["PROYECTOS", data.status.projects ?? 0, theme.violet], ["EN CURSO", data.status.active_dispatches ?? 0, theme.cyan],
          ["POR APROBAR", pending, theme.amber], ["BLOQUEADAS", blocked, theme.coral]].map(([label, value, color]) =>
          <box key={String(label)} flexGrow={1} flexBasis={0} border borderStyle="rounded" borderColor={theme.border} backgroundColor={theme.panel} paddingX={1} flexDirection="column">
            <text fg={String(color)}><b>{value}</b></text><text fg={theme.muted}>{width < 65 ? ({ PROYECTOS: "PROY.", "EN CURSO": "ACTIVAS", "POR APROBAR": "ESPERA", BLOQUEADAS: "BLOQ." } as Record<string, string>)[String(label)] : label}</text>
          </box>)}
      </box>
      {data.tasks.length === 0 && <Panel title="Empieza por un objetivo" grow={0}>
        <box flexDirection="column" gap={1} paddingY={1}><text fg={theme.text}>Convierte una idea en fases y tareas con seguimiento.</text>
          <Hint>Registra tu proyecto, define un requisito y prepara la primera tarea.</Hint>
          <box flexDirection="row" gap={1} flexWrap="wrap"><Action label="2 Registrar proyecto →" onPress={() => onNavigate(1)} /><Action label="3 Planificar →" onPress={() => onNavigate(2)} /><Action label="4 Crear tarea →" onPress={() => onNavigate(3)} /></box>
        </box>
      </Panel>}
      <box flexDirection={width < 80 ? "column" : "row"} gap={1}>
        <Panel title="Fases"><box flexDirection="column" paddingY={0} gap={0}>
          {data.phases.length === 0 ? <Hint>Sin fases. En Planificación puedes crear la primera.</Hint> : data.phases.slice(0, 6).map((phase) => {
            const progress = Math.max(0, Math.min(1, phase.progress ?? 0)); const filled = Math.round(progress * 10);
            return <box key={phase.phase_id} flexDirection="column"><text fg={theme.text}>{clean(phase.name ?? phase.phase_id)}</text>
              <text fg={statusColor(phase.status ?? "planned")}>{"━".repeat(filled)}<span fg={theme.border}>{"─".repeat(10 - filled)}</span> {Math.round(progress * 100)}% <span fg={theme.muted}>{phase.completed_tasks ?? 0}/{phase.total_tasks ?? 0}</span></text></box>;
          })}
        </box></Panel>
        <Panel title="Agentes"><box flexDirection="column" paddingY={0} gap={0}>
          {data.agents.length === 0 ? <Hint>Sin actividad de agentes. Consulta el coordinador en Integraciones.</Hint> : data.agents.slice(0, 6).map((agent) =>
            <text key={agent.agent_id} fg={theme.violet}>● {clean(agent.agent_id)}<span fg={theme.muted}>  {agent.active ?? 0} activas · {agent.completed ?? 0} completas</span></text>)}
        </box></Panel>
      </box>
      <Panel title="Cola de trabajo"><box flexDirection="column" paddingY={0} gap={0}>
        <text fg={theme.muted}>ESTADO / OBJETIVO · AGENTE · ORIGEN</text>
        {data.tasks.length === 0 ? <Hint>La cola está vacía. Las nuevas tareas esperan tu aprobación.</Hint> : data.tasks.slice(0, 8).map((task) =>
          <box key={task.task_id} flexDirection="column"><text fg={theme.text}><span fg={statusColor(task.state ?? "planned")}>● {statusLabel(task.state ?? "planned")} </span>{clean(task.objective ?? task.task_id)}</text>
            <Hint>{clean(task.actor)} · {clean(task.source)} · {clean(task.task_id)}</Hint></box>)}
        {data.tasks.length > 8 && <Action label={`Ver las ${data.tasks.length} tareas →`} onPress={() => onNavigate(3)} />}
      </box></Panel>
    </box>
  </scrollbox>;
}
