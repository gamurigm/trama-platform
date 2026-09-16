import type { ScreenId } from "../navigation/model";
import { colors } from "../ui/tokens";

export const screenTitles: Record<ScreenId, string> = {
  dashboard: "Dashboard",
  projects: "Projects",
  tasks: "Tasks",
  agents: "Agents",
  queues: "Queues",
  workers: "Workers",
  events: "Events",
  memory: "Memory",
  health: "System health",
};

export const screenIds = Object.keys(screenTitles) as ScreenId[];

export function NavigationRail({ screen, onChoose, compact = false }: { screen: ScreenId; onChoose: (screen: ScreenId) => void; compact?: boolean }) {
  if (compact) {
    return (
      <box border borderStyle="single" title="Navegación" titleColor={colors.focus} padding={1} width="100%">
        <text wrapMode="none">
          <span fg={colors.focus}>▌ </span>{screenTitles[screen]} <span fg={colors.muted}>· j/k o / para cambiar</span>
        </text>
      </box>
    );
  }

  return (
    <box border borderStyle="single" title="Navegación" titleColor={colors.focus} flexDirection="column" padding={1} width={20}>
      {screenIds.map((item) => (
        <text key={item} wrapMode="none" onMouseUp={() => onChoose(item)}>
          <span fg={item === screen ? colors.focus : colors.muted}>{item === screen ? "▌" : " "} </span>
          {screenTitles[item]}
        </text>
      ))}
    </box>
  );
}
