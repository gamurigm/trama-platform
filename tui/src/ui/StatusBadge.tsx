import { colors } from "./tokens";

type StatusState = "active" | "success" | "blocked" | "pending" | "unavailable" | "error" | string;

const statusStyles: Record<string, { symbol: string; color: string }> = {
  active: { symbol: "›", color: colors.focus },
  running: { symbol: "›", color: colors.focus },
  success: { symbol: "✓", color: "#86EFAC" },
  succeeded: { symbol: "✓", color: "#86EFAC" },
  completed: { symbol: "✓", color: "#86EFAC" },
  blocked: { symbol: "!", color: colors.danger },
  failed: { symbol: "!", color: colors.danger },
  error: { symbol: "!", color: colors.danger },
  pending: { symbol: "○", color: colors.attention },
  planned: { symbol: "○", color: colors.attention },
  unavailable: { symbol: "·", color: colors.muted },
};

const fallbackStyle = { symbol: "·", color: colors.muted };

export function StatusBadge({ state, label }: { state: StatusState; label: string }) {
  const style = statusStyles[state.toLowerCase()] ?? fallbackStyle;
  return (
    <text>
      <span fg={style.color}>{style.symbol} </span>
      {label}
    </text>
  );
}
