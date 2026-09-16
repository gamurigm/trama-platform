import { useCallback, useEffect, useRef, useState } from "react";
import { useKeyboard, useRenderer, useTerminalDimensions } from "@opentui/react";
import { StatusBar } from "./components/StatusBar";
import type { DashboardData } from "./api/types";
import type { ScreenData, TaskAction } from "./api/types";
import type { TramaApiClient } from "./api/client";
import { initialNavigation, reduceNavigation } from "./navigation/reducer";
import type { ScreenId } from "./navigation/model";
import { DashboardScreen } from "./screens/DashboardScreen";
import { NavigationRail, screenIds, screenTitles } from "./screens/NavigationRail";
import { CommandPalette, type PaletteCommand } from "./ui/CommandPalette";
import { KeyHints } from "./ui/KeyHints";
import { colors } from "./ui/tokens";
import { ProjectsScreen } from "./screens/ProjectsScreen";
import { TasksScreen } from "./screens/TasksScreen";
import { AgentsScreen } from "./screens/AgentsScreen";
import { QueuesScreen } from "./screens/QueuesScreen";
import { WorkersScreen } from "./screens/WorkersScreen";
import { EventsScreen } from "./screens/EventsScreen";
import { MemoryScreen } from "./screens/MemoryScreen";
import { HealthScreen } from "./screens/HealthScreen";
import { ConfirmDialog } from "./ui/ConfirmDialog";
import { ProjectPicker } from "./ui/ProjectPicker";

type AppState =
  | { status: "loading" }
  | { status: "ready"; data: DashboardData; staleSince?: number; error?: Error }
  | { status: "error"; error: Error };

type PendingAction = { taskId: string; action: TaskAction };

export function App({ client, pollMs = 2000 }: { client: TramaApiClient; pollMs?: number }) {
  const renderer = useRenderer();
  const { width } = useTerminalDimensions();
  const [state, setState] = useState<AppState>({ status: "loading" });
  const [screenData, setScreenData] = useState<ScreenData>({});
  const [pendingAction, setPendingAction] = useState<PendingAction>();
  const [navigation, setNavigation] = useState(initialNavigation);
  const requestInFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    try {
      const data = await client.getDashboard(navigation.projectId);
      setState({ status: "ready", data });
    } catch (error) {
      const normalizedError = error instanceof Error ? error : new Error(String(error));
      setState((current) => current.status === "ready"
        ? { ...current, staleSince: Date.now(), error: normalizedError }
        : { status: "error", error: normalizedError });
    } finally {
      requestInFlight.current = false;
    }
  }, [client, navigation.projectId]);

  const requestTaskAction = useCallback((action: TaskAction, explicitTaskId?: string) => {
    if (navigation.screen !== "tasks" || navigation.overlay !== "none") return;
    const taskId = explicitTaskId ?? navigation.selectedId ?? (state.status === "ready" ? state.data.tasks[0]?.task_id : undefined);
    if (!taskId) return;
    setPendingAction({ taskId, action });
    setNavigation((current) => reduceNavigation(current, { type: "open-overlay", overlay: "confirm" }));
  }, [navigation.overlay, navigation.screen, navigation.selectedId, state]);

  const executeTaskAction = useCallback(async () => {
    if (!pendingAction) return;
    try {
      if (pendingAction.action === "approve") await client.approveTask(pendingAction.taskId);
      if (pendingAction.action === "cancel") await client.cancelTask(pendingAction.taskId);
      if (pendingAction.action === "retry") await client.retryTask(pendingAction.taskId);
      setNavigation((current) => reduceNavigation(current, {
        type: "set-notice",
        notice: { kind: "success", message: `${pendingAction.action} enviado para ${pendingAction.taskId}` },
      }));
      setNavigation((current) => reduceNavigation(current, { type: "close-overlay" }));
      setPendingAction(undefined);
      void refresh();
    } catch (error) {
      setNavigation((current) => reduceNavigation(current, {
        type: "set-notice",
        notice: { kind: "error", message: error instanceof Error ? error.message : String(error) },
      }));
      setNavigation((current) => reduceNavigation(current, { type: "close-overlay" }));
      setPendingAction(undefined);
    }
  }, [client, pendingAction, refresh]);

  useEffect(() => {
    if (navigation.overlay !== "none") return;
    void refresh();
    const interval = setInterval(() => void refresh(), pollMs);
    return () => clearInterval(interval);
  }, [navigation.overlay, pollMs, refresh]);

  useEffect(() => {
    if (navigation.screen === "dashboard") return;
    let cancelled = false;
    const load = async () => {
      try {
        if (navigation.screen === "projects") {
          const projects = await client.listProjects();
          if (!cancelled) setScreenData((current) => ({ ...current, projects }));
        } else if (navigation.screen === "agents") {
          const agents = await client.listAgents();
          if (!cancelled) setScreenData((current) => ({ ...current, agents }));
        } else if (navigation.screen === "events") {
          const events = await client.listEvents();
          if (!cancelled) setScreenData((current) => ({ ...current, events }));
        } else if (navigation.screen === "memory") {
          if (!navigation.projectId) return;
          const projects = await client.listProjects();
          const project = projects.find((item) => item.project_id === navigation.projectId);
          if (project) {
            const memory = await client.listMemoryCandidates(project.organization_id ?? "default", project.project_id);
            if (!cancelled) setScreenData((current) => ({ ...current, memory, projects }));
          }
        } else if (navigation.screen === "health") {
          const health = await client.getHealth();
          if (!cancelled) setScreenData((current) => ({ ...current, health }));
        }
      } catch (error) {
        if (!cancelled) setScreenData((current) => ({ ...current, logs: [{ message: error instanceof Error ? error.message : String(error), project_id: navigation.projectId ?? "", correlation_id: "screen-load" }] }));
      }
    };
    void load();
    return () => { cancelled = true; };
  }, [client, navigation.projectId, navigation.screen]);

  useEffect(() => {
    if (navigation.overlay !== "project-picker" || screenData.projects) return;
    void client.listProjects().then((projects) => setScreenData((current) => ({ ...current, projects }))).catch(() => undefined);
  }, [client, navigation.overlay, screenData.projects]);

  useKeyboard((key) => {
    const name = String(key.name);
    const sequence = String(key.sequence);
    const normalizedName = name.toLowerCase();
    const input = normalizedName === "slash" || sequence === "/" ? "/" : name;
    if (navigation.overlay !== "none") {
      if (normalizedName === "escape" || normalizedName === "esc") {
        setNavigation((current) => reduceNavigation(current, { type: "close-overlay" }));
      }
      return;
    }
    if (normalizedName === "r") void refresh();
    if (normalizedName === "q") renderer.destroy();
    if (normalizedName === "down" || normalizedName === "arrowdown" || normalizedName === "j" || normalizedName === "up" || normalizedName === "arrowup" || normalizedName === "k") {
      const direction = normalizedName === "up" || normalizedName === "arrowup" || normalizedName === "k" ? -1 : 1;
      setNavigation((current) => {
        const currentIndex = screenIds.indexOf(current.screen);
        const nextScreen = screenIds[(currentIndex + direction + screenIds.length) % screenIds.length] ?? "dashboard";
        return reduceNavigation(current, { type: "open-screen", screen: nextScreen });
      });
      return;
    }
    if (normalizedName === "a" || normalizedName === "x" || normalizedName === "y") {
      requestTaskAction(normalizedName === "a" ? "approve" : normalizedName === "x" ? "cancel" : "retry");
    }
    if (input === "/" || input === "?" || normalizedName === "p") {
      setNavigation((current) => {
        const next = reduceNavigation(current, { type: "key", key: input === "/" ? "/" : name, itemCount: 0 });
        return next;
      });
    }
  });

  if (state.status === "loading") {
    return <box flexGrow={1} alignItems="center" justifyContent="center"><text>Conectando...</text></box>;
  }

  if (state.status === "error") {
    return <box flexGrow={1} alignItems="center" justifyContent="center"><text>API no disponible: {state.error.message}</text></box>;
  }

  const stacked = width < 60;
  const commands: PaletteCommand[] = [
    ...screenIds.map((screen) => ({ id: screen, label: screenTitles[screen], screen })),
    { id: "refresh", label: "Actualizar" },
    { id: "project", label: "Cambiar proyecto" },
    { id: "help", label: "Ayuda" },
    { id: "quit", label: "Salir" },
  ];
  const screen = navigation.screen;
  const routedData: ScreenData = { ...screenData, tasks: state.data.tasks, agents: state.data.agents, status: state.data.status };

  const operationalScreen = screen === "projects" ? <ProjectsScreen projectId={navigation.projectId} data={routedData} selectedId={navigation.selectedId} />
    : screen === "tasks" ? <TasksScreen projectId={navigation.projectId} data={routedData} selectedId={navigation.selectedId} onAction={(taskId, action) => { setNavigation((current) => reduceNavigation(current, { type: "select-id", id: taskId, index: 0 })); requestTaskAction(action, taskId); }} />
      : screen === "agents" ? <AgentsScreen projectId={navigation.projectId} data={routedData} selectedId={navigation.selectedId} />
        : screen === "queues" ? <QueuesScreen projectId={navigation.projectId} data={routedData} />
          : screen === "workers" ? <WorkersScreen projectId={navigation.projectId} data={routedData} />
            : screen === "events" ? <EventsScreen projectId={navigation.projectId} data={routedData} selectedId={navigation.selectedId} />
              : screen === "memory" ? <MemoryScreen projectId={navigation.projectId} data={routedData} selectedId={navigation.selectedId} />
                : <HealthScreen projectId={navigation.projectId} data={routedData} />;

  return (
    <box flexDirection="column" width="100%" height="100%">
      <box border borderStyle="single" paddingLeft={1} paddingRight={1}>
        <text><strong fg={colors.focus}>TRAMA</strong>{"  ·  "}{screenTitles[screen]}{"  ·  "}<span fg={colors.focus}>API ●</span></text>
      </box>
      <StatusBar status={state.data.status} />
      {"staleSince" in state && state.staleSince ? <text fg={colors.attention}>{`Datos obsoletos · ${state.error?.message ?? "actualiza con r"}`}</text> : null}
      <box flexDirection={stacked ? "column" : "row"} flexGrow={1}>
        <NavigationRail screen={screen} compact={stacked} onChoose={(nextScreen: ScreenId) => setNavigation((current) => reduceNavigation(current, { type: "open-screen", screen: nextScreen }))} />
        {screen === "dashboard" ? (
          <DashboardScreen data={state.data} stacked={stacked} />
        ) : (
          operationalScreen
        )}
      </box>
      <box border borderStyle="single" paddingLeft={1} paddingRight={1}>
        <KeyHints items={stacked
          ? [{ key: "j/k", label: "mover" }, { key: "/", label: "comandos" }, { key: "r", label: "actualizar" }, { key: "q", label: "salir" }]
          : [{ key: "↑↓/jk", label: "navegar" }, { key: "Enter", label: "abrir" }, { key: "/", label: "comandos" }, { key: "r", label: "actualizar" }, { key: "q", label: "salir" }]}
        />
      </box>
      {navigation.overlay === "palette" ? <CommandPalette commands={commands} onChoose={(command) => command.screen && setNavigation((current) => reduceNavigation(current, { type: "open-screen", screen: command.screen as ScreenId }))} onClose={() => setNavigation((current) => reduceNavigation(current, { type: "close-overlay" }))} /> : null}
      {navigation.overlay === "project-picker" ? <ProjectPicker projects={screenData.projects ?? []} onChoose={(project) => { setNavigation((current) => reduceNavigation(current, { type: "set-project", projectId: project.project_id })); setNavigation((current) => reduceNavigation(current, { type: "close-overlay" })); }} onClose={() => setNavigation((current) => reduceNavigation(current, { type: "close-overlay" }))} /> : null}
      {navigation.overlay === "confirm" && pendingAction ? <ConfirmDialog action={pendingAction.action} target={pendingAction.taskId} consequence="La operación se enviará a la API y puede cambiar el estado de la tarea." onConfirm={() => void executeTaskAction()} onCancel={() => { setPendingAction(undefined); setNavigation((current) => reduceNavigation(current, { type: "close-overlay" })); }} /> : null}
      {navigation.notice ? <text fg={navigation.notice.kind === "error" ? colors.danger : colors.focus}>{navigation.notice.message}</text> : null}
    </box>
  );
}
