export const theme = {
  bg: "#0B1020", panel: "#10192B", raised: "#18243C", border: "#293B58",
  text: "#E6EDF7", muted: "#91A3BE", violet: "#B79AFF", cyan: "#67DBE8",
  amber: "#F5C779", coral: "#FF8B94", green: "#79DCAE", selected: "#293659",
};
const labels: Record<string, string> = {
  connected: "conectado", unreachable: "sin respuesta", not_configured: "sin configurar",
  available: "disponible",
  not_installed: "no instalado", stopped: "detenido", not_implemented: "no implementado",
  planned: "por aprobar", proposed: "propuesto", approved: "aprobado", accepted: "en cola",
  running: "en curso", in_progress: "en curso", succeeded: "completado", completed: "completado",
  failed: "falló", blocked: "bloqueado", cancelled: "cancelado", ready: "listo", partial: "parcial",
};
export function statusLabel(value: string) { return labels[value.toLowerCase()] ?? value; }
export function statusColor(value: string) {
  if (["failed", "blocked", "unreachable", "error"].includes(value.toLowerCase())) return theme.coral;
  if (["planned", "proposed", "not_installed", "not_configured", "stopped", "partial"].includes(value.toLowerCase())) return theme.amber;
  if (["connected", "succeeded", "completed", "approved"].includes(value.toLowerCase())) return theme.green;
  return theme.cyan;
}
export const clean = (value: unknown) => String(value ?? "—").replace(/[\u0000-\u001f\u007f-\u009f]/g, " ");
