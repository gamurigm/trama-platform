import type { Status } from "../api/types";

function valueOrDash(value: unknown): string {
  return typeof value === "string" || typeof value === "number" ? String(value) : "-";
}

export function StatusBar({ status }: { status: Status }) {
  return (
    <box border borderStyle="single" paddingLeft={1} paddingRight={1}>
      <text>
        <strong fg="#7dd3fc">TRAMA</strong>
        {"  "}
        <span fg={status.status === "ok" ? "#86efac" : "#facc15"}>
          estado: {valueOrDash(status.status)}
        </span>
        {"  proyectos: "}{valueOrDash(status.projects)}
        {"  cola: "}{valueOrDash(status.queue_depth)}
        {"  dispatches: "}{valueOrDash(status.active_dispatches)}
      </text>
    </box>
  );
}
