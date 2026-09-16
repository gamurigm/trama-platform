import { Panel } from "../ui/Panel";
import type { Worker } from "../api/types";
import { OperationalFrame, emptyMessage, type ScreenProps } from "./OperationalFrame";

export function WorkersScreen({ projectId, data }: ScreenProps) {
  const workers = data.workers ?? [];
  return (
    <OperationalFrame title="Workers" projectId={projectId}>
      <Panel title="Workers" accent="focus">
        {workers.length === 0 ? <text>{emptyMessage("workers")}</text> : workers.map((worker: Worker) => (
          <text key={worker.worker_id} wrapMode="none">{`${worker.worker_id}  estado: ${worker.status ?? "no disponible"}  capacidad: ${worker.capacity ?? "no disponible"}`}</text>
        ))}
      </Panel>
    </OperationalFrame>
  );
}
