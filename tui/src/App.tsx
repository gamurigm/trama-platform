import { useCallback, useEffect, useRef, useState } from "react";
import { useKeyboard, useRenderer, useTerminalDimensions } from "@opentui/react";
import { AgentsPanel } from "./components/AgentsPanel";
import { PhasePanel } from "./components/PhasePanel";
import { StatusBar } from "./components/StatusBar";
import { TaskTable } from "./components/TaskTable";
import type { DashboardData } from "./api/types";
import type { TramaApiClient } from "./api/client";

type AppState =
  | { status: "loading" }
  | { status: "ready"; data: DashboardData }
  | { status: "error"; error: Error };

export function App({ client, pollMs = 2000 }: { client: TramaApiClient; pollMs?: number }) {
  const renderer = useRenderer();
  const { width } = useTerminalDimensions();
  const [state, setState] = useState<AppState>({ status: "loading" });
  const requestInFlight = useRef(false);

  const refresh = useCallback(async () => {
    if (requestInFlight.current) return;
    requestInFlight.current = true;
    try {
      const data = await client.getDashboard();
      setState({ status: "ready", data });
    } catch (error) {
      setState({ status: "error", error: error instanceof Error ? error : new Error(String(error)) });
    } finally {
      requestInFlight.current = false;
    }
  }, [client]);

  useEffect(() => {
    void refresh();
    const interval = setInterval(() => void refresh(), pollMs);
    return () => clearInterval(interval);
  }, [pollMs, refresh]);

  useKeyboard((key) => {
    if (key.name === "r") void refresh();
    if (key.name === "q") renderer.destroy();
  });

  if (state.status === "loading") {
    return <box flexGrow={1} alignItems="center" justifyContent="center"><text>Conectando...</text></box>;
  }

  if (state.status === "error") {
    return <box flexGrow={1} alignItems="center" justifyContent="center"><text>API no disponible: {state.error.message}</text></box>;
  }

  const stacked = width < 60;

  return (
    <box flexDirection="column" width="100%" height="100%">
      <StatusBar status={state.data.status} />
      <box flexDirection={stacked ? "column" : "row"} flexGrow={1}>
        <box flexDirection="column" width={stacked ? "100%" : "40%"} flexGrow={stacked ? 1 : undefined}>
          <PhasePanel phases={state.data.phases} />
          <AgentsPanel agents={state.data.agents} />
        </box>
        <TaskTable tasks={state.data.tasks} />
      </box>
    </box>
  );
}
