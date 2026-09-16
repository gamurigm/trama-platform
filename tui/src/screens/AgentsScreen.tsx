import { Panel } from "../ui/Panel";
import type { Agent } from "../api/types";
import { OperationalFrame, type ScreenProps } from "./OperationalFrame";

export function AgentsScreen({ projectId, data, selectedId, onSelect }: ScreenProps) {
  const agents = data.agents ?? [];
  return (
    <OperationalFrame title="Agents" projectId={projectId}>
      <Panel title="Agentes conectados" accent="cognitive">
        {agents.length === 0 ? <text>no hay agentes</text> : agents.map((agent: Agent) => (
          <text key={agent.agent_id} wrapMode="none" onMouseUp={() => onSelect?.(agent.agent_id)}>
            {`${selectedId === agent.agent_id ? "›" : " "} ${agent.agent_id}  tareas: ${agent.tasks ?? "no disponible"}  activas: ${agent.active ?? "no disponible"}`}
          </text>
        ))}
      </Panel>
    </OperationalFrame>
  );
}
