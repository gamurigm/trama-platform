import type { Agent } from "../api/types";

function count(value: unknown): string {
  return typeof value === "number" ? String(value) : "-";
}

function agentName(value: unknown): string {
  return typeof value === "string" && value.trim() ? value : "-";
}

export function AgentsPanel({ agents, compact = false }: { agents: Agent[]; compact?: boolean }) {
  if (compact) {
    return (
      <box flexDirection="column" padding={0} flexGrow={0} height={Math.max(1, agents.length + 1)}>
        <text fg="#c4b5fd">Agentes CCCC</text>
        {agents.length === 0 ? (
          <text fg="#94a3b8">sin agentes registrados</text>
        ) : (
          agents.map((agent) => (
            <text key={agent.agent_id} wrapMode="none" fg="#c4b5fd">{`${agentName(agent.agent_id)}  activos: ${count(agent.active)}  completadas: ${count(agent.completed)}`}</text>
          ))
        )}
      </box>
    );
  }

  return (
    <box border borderStyle="single" title="Agentes CCCC" titleColor="#c4b5fd" flexDirection="column" padding={1} flexGrow={1}>
      {agents.length === 0 ? (
        <text fg="#94a3b8">sin agentes registrados</text>
      ) : (
        agents.map((agent) => (
          <text key={agent.agent_id} wrapMode={compact ? "none" : undefined}>
            <strong fg="#c4b5fd">{agentName(agent.agent_id)}</strong>
            {compact
              ? `  activos: ${count(agent.active)}  completadas: ${count(agent.completed)}`
              : `  activos: ${count(agent.active)}  completadas: ${count(agent.completed)}  tareas: ${count(agent.tasks)}  bloqueadas: ${count(agent.blocked)}`}
          </text>
        ))
      )}
    </box>
  );
}
