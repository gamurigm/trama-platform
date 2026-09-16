import { Panel } from "../ui/Panel";
import type { OperationEvent } from "../api/types";
import { StatusBadge } from "../ui/StatusBadge";
import { OperationalFrame, type ScreenProps } from "./OperationalFrame";

export function EventsScreen({ projectId, data, selectedId, onSelect }: ScreenProps) {
  const events = data.events?.filter((event) => !projectId || !event.project_id || event.project_id === projectId) ?? [];
  return (
    <OperationalFrame title="Events" projectId={projectId}>
      <Panel title="Operation events" accent="focus">
        {events.length === 0 ? <text>no hay eventos</text> : events.map((event: OperationEvent) => (
          <box key={event.event_id ?? `${event.action}-${event.created_at}`} flexDirection="row" onMouseUp={() => event.event_id && onSelect?.(event.event_id)}>
            <StatusBadge state={event.status} label={`${selectedId === event.event_id ? "› " : "  "}${event.action} · ${event.actor ?? "system"}`} />
          </box>
        ))}
      </Panel>
    </OperationalFrame>
  );
}
