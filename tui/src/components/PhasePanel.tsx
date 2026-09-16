import type { Phase } from "../api/types";

const BAR_WIDTH = 10;

function stateIcon(state: string | undefined): string {
  const normalized = state?.toLowerCase();
  if (normalized === "running" || normalized === "active" || normalized === "in_progress") return "›";
  if (normalized === "blocked" || normalized === "failed" || normalized === "error") return "!";
  if (normalized === "success" || normalized === "completed" || normalized === "done") return "✓";
  return "○";
}

function isBlocked(state: string | undefined): boolean {
  return state?.toLowerCase() === "blocked";
}

function progressBar(progress: number | undefined): string {
  const bounded = Math.max(0, Math.min(1, progress ?? 0));
  const filled = Math.round(bounded * BAR_WIDTH);
  return "█".repeat(filled) + "░".repeat(BAR_WIDTH - filled);
}

function progressLabel(progress: number | undefined): string {
  return `${Math.round(Math.max(0, Math.min(1, progress ?? 0)) * 100)}%`;
}

function phaseName(phase: Phase): string {
  return typeof phase.name === "string" && phase.name.trim() ? phase.name : phase.phase_id;
}

export function PhasePanel({ phases }: { phases: Phase[] }) {
  return (
    <box border borderStyle="single" title="Fases" titleColor="#7dd3fc" flexDirection="column" padding={1} flexGrow={1}>
      {phases.length === 0 ? (
        <text fg="#94a3b8">sin fases configuradas</text>
      ) : (
        phases.map((phase) => (
          <text key={phase.phase_id} wrapMode="none">
            <span fg={isBlocked(phase.status) ? "#f87171" : "#86efac"}>{stateIcon(phase.status)} </span>
            <strong>{phaseName(phase)}</strong>
            {" "}{progressBar(phase.progress)} {progressLabel(phase.progress)}
            {phase.completed_tasks !== undefined && phase.total_tasks !== undefined
              ? ` ${phase.completed_tasks}/${phase.total_tasks}`
              : ""}
          </text>
        ))
      )}
    </box>
  );
}
