import { useCallback, useEffect, useRef, useState } from "react";
import { useKeyboard, useRenderer, useTerminalDimensions } from "@opentui/react";
import { StatusBar } from "./components/StatusBar";
import type { DashboardData } from "./api/types";
import type { ScreenData } from "./api/types";
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

type AppState =
  | { status: "loading" }
  | { status: "ready"; data: DashboardData }
  | { status: "error"; error: Error };

export function App({ client, pollMs = 2000 }: { client: TramaApiClient; pollMs?: number }) {
  const renderer = useRenderer();
  const { width } = useTerminalDimensions();
  const [state, setState] = useState<AppState>({ status: "loading" });
  const [screenData, setScreenData] = useState<ScreenData>({});
  const [navigation, setNavigation] = useState(initialNavigation);
  const requestInFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    try {
      const data = await client.getDashboard(navigation.projectId);
      setState({ status: "ready", data });
    } catch (error) {
      setState({ status: "error", error: error instanceof Error ? error : new Error(String(error)) });
    } finally {
      requestInFlight.current = false;
    }
  }, [client, navigation.projectId]);

  useEffect(() => {
    void refresh();
    const interval = setInterval(() => void refresh(), pollMs);
    return () => clearInterval(interval);
  }, [pollMs, refresh]);

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
    : screen === "tasks" ? <TasksScreen projectId={navigation.projectId} data={routedData} selectedId={navigation.selectedId} />
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
      {navigation.overlay === "palette" ? <CommandPalette commands={commands} onChoose={(command) => command.screen && setNavigation((current) => reduceNavigation(current, { type: "open-screen", screen: command.screen as ScreenId }))} /> : null}
    </box>
  );
}
