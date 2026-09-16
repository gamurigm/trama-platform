import { Panel } from "../ui/Panel";
import type { MemoryCandidate } from "../api/types";
import { OperationalFrame, type ScreenProps } from "./OperationalFrame";

export function MemoryScreen({ projectId, data, selectedId, onSelect }: ScreenProps) {
  const candidates = data.memory?.filter((candidate) => !projectId || candidate.project_id === projectId) ?? [];
  return (
    <OperationalFrame title="Memory" projectId={projectId}>
      <Panel title="Candidatos de memoria" accent="cognitive">
        {candidates.length === 0 ? <text>no hay candidatos</text> : candidates.map((candidate: MemoryCandidate) => (
          <text key={candidate.candidate_id} wrapMode="none" onMouseUp={() => onSelect?.(candidate.candidate_id)}>
            {`${selectedId === candidate.candidate_id ? "›" : " "} ${candidate.subject} · ${candidate.status ?? "no disponible"} · ${Math.round((candidate.confidence ?? 0) * 100)}%`}
          </text>
        ))}
      </Panel>
    </OperationalFrame>
  );
}
