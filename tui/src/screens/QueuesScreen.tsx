import { Panel } from "../ui/Panel";
import { OperationalFrame, emptyMessage, type ScreenProps } from "./OperationalFrame";

export function QueuesScreen({ projectId, data }: ScreenProps) {
  const status = data.status;
  return (
    <OperationalFrame title="Queues" projectId={projectId}>
      <Panel title="Cola y dispatch" accent="attention">
        <text>{`profundidad: ${status?.queue_depth ?? "no disponible"}`}</text>
        <text>{`capacidad: ${status?.queue_capacity ?? "no disponible"}`}</text>
        <text>{`dispatches activos: ${status?.active_dispatches ?? "no disponible"}`}</text>
        <text>{`estado dispatcher: ${status?.dispatcher_status ?? emptyMessage("dispatcher")}`}</text>
      </Panel>
    </OperationalFrame>
  );
}
