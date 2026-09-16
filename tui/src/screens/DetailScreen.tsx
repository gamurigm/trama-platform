import type { TimelineEntry } from "../api/types";
import { Panel } from "../ui/Panel";
import { OperationalFrame } from "./OperationalFrame";

export function DetailScreen({ kind, id, projectId, timeline }: { kind: string; id: string; projectId?: string; timeline: TimelineEntry[] }) {
  return (
    <OperationalFrame title={`${kind} · ${id}`} projectId={projectId}>
      <Panel title="Timeline" accent="focus">
        {timeline.length === 0 ? <text>timeline vacío</text> : [...timeline].sort((left, right) => left.sequence - right.sequence).map((entry) => (
          <text key={entry.entry_id} wrapMode="none">{`${entry.sequence}. ${entry.action ?? entry.kind} · ${entry.status ?? "no disponible"} · ${entry.actor}`}</text>
        ))}
      </Panel>
    </OperationalFrame>
  );
}
