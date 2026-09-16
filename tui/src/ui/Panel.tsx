import type { ReactNode } from "react";
import { borders, colors, spacing, type Accent } from "./tokens";

type PanelProps = {
  title: string;
  accent?: Accent;
  children: ReactNode;
  flexGrow?: number;
  width?: number | `${number}%` | "auto";
};

export function Panel({ title, accent = "focus", children, flexGrow, width }: PanelProps) {
  return (
    <box
      border
      borderStyle={borders.style}
      title={title}
      titleColor={colors[accent]}
      flexDirection="column"
      padding={spacing.panel}
      flexGrow={flexGrow}
      width={width}
    >
      {children}
    </box>
  );
}
