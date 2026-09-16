import type { ScreenId } from "../navigation/model";
import { screenTitles } from "../screens/NavigationRail";
import { colors } from "./tokens";

export type PaletteCommand = { id: string; label: string; screen?: ScreenId };

export function CommandPalette({ commands, query = "", onChoose }: { commands: PaletteCommand[]; query?: string; onChoose: (command: PaletteCommand) => void }) {
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = commands.filter((command) => command.label.toLowerCase().includes(normalizedQuery));
  return (
    <box position="absolute" top={3} left={2} right={2} zIndex={10} backgroundColor={colors.panel} border borderStyle="double" title="Command palette" titleColor={colors.focus} flexDirection="column" padding={1}>
      <text fg={colors.muted}>Escribe un comando o usa ↑/↓ y Enter</text>
      {filtered.slice(0, 8).map((command) => (
        <text key={command.id} wrapMode="none">
          <span fg={colors.focus}>› </span>{command.screen ? screenTitles[command.screen] : command.label}
        </text>
      ))}
    </box>
  );
}
