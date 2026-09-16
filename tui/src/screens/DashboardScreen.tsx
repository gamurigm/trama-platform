import type { DashboardData } from "../api/types";
import { AgentsPanel } from "../components/AgentsPanel";
import { PhasePanel } from "../components/PhasePanel";
import { TaskTable } from "../components/TaskTable";
import { ActivityPanel } from "./ActivityPanel";

export function DashboardScreen({ data, stacked }: { data: DashboardData; stacked: boolean }) {
  if (stacked) {
    return (
      <box flexDirection="column" flexGrow={1}>
        <text><strong fg="#63E6E2">Dashboard</strong>  radar operativo</text>
        <PhasePanel phases={data.phases} compact />
        <AgentsPanel agents={data.agents} compact />
        <TaskTable tasks={data.tasks} compact />
      </box>
    );
  }

  return (
    <box flexDirection="column" flexGrow={1}>
      <text><strong fg="#63E6E2">Dashboard</strong>  radar operativo</text>
      <box flexDirection={stacked ? "column" : "row"} flexGrow={1}>
        <box flexDirection="column" width={stacked ? "100%" : "42%"} flexGrow={stacked ? 1 : undefined}>
          <PhasePanel phases={data.phases} />
          <AgentsPanel agents={data.agents} />
        </box>
        <box flexDirection="column" flexGrow={1}>
          <TaskTable tasks={data.tasks} />
          <ActivityPanel tasks={data.tasks} />
        </box>
      </box>
    </box>
  );
}
