import { Panel } from "../ui/Panel";
import { StatusBadge } from "../ui/StatusBadge";
import { OperationalFrame, type ScreenProps } from "./OperationalFrame";

export function HealthScreen({ projectId, data }: ScreenProps) {
  const health = data.health;
  return (
    <OperationalFrame title="System health" projectId={projectId}>
      <Panel title="Health checks" accent="focus">
        <StatusBadge state={health?.status ?? "unavailable"} label={health?.status ?? "no disponible"} />
        <text>{`servicio: ${health?.service ?? "no disponible"}`}</text>
        <text>{`dispatcher: ${data.status?.dispatcher_status ?? "no disponible"}`}</text>
      </Panel>
    </OperationalFrame>
  );
}
