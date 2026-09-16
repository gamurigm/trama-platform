import { useKeyboard } from "@opentui/react";
import { useState } from "react";
import type { ScreenId } from "../navigation/model";
import { screenTitles } from "../screens/NavigationRail";
import { colors } from "./tokens";

export type PaletteCommand = { id: string; label: string; screen?: ScreenId };

export function CommandPalette({ commands, query = "", onChoose, onClose }: { commands: PaletteCommand[]; query?: string; onChoose: (command: PaletteCommand) => void; onClose: () => void }) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  const normalizedQuery = query.trim().toLowerCase();
  const filtered = commands.filter((command) => command.label.toLowerCase().includes(normalizedQuery));
  useKeyboard((key) => {
    const name = String(key.name).toLowerCase();
    if (name === "escape" || name === "esc") return onClose();
    if (name === "down" || name === "arrowdown" || name === "j") {
      return setSelectedIndex((current) => filtered.length ? (current + 1) % filtered.length : 0);
    }
    if (name === "up" || name === "arrowup" || name === "k") {
      return setSelectedIndex((current) => filtered.length ? (current - 1 + filtered.length) % filtered.length : 0);
    }
    if (name === "enter" || name === "return") {
      const command = filtered[selectedIndex];
      if (command) onChoose(command);
    }
    if (/^[1-9]$/.test(name)) {
      const command = filtered[Number(name) - 1];
      if (command) onChoose(command);
    }
  });
  return (
    <box position="absolute" top={3} left={2} right={2} zIndex={10} backgroundColor={colors.panel} border borderStyle="double" title="Command palette" titleColor={colors.focus} flexDirection="column" padding={1}>
      <text fg={colors.muted}>Escribe un comando o usa ↑/↓ y Enter</text>
      {filtered.slice(0, 8).map((command, index) => (
        <text key={command.id} wrapMode="none">
          <span fg={index === selectedIndex ? colors.focus : colors.muted}>{index === selectedIndex ? "› " : "  "}</span>{command.screen ? screenTitles[command.screen] : command.label}
        </text>
      ))}
    </box>
  );
}
