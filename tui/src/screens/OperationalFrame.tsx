import type { ReactNode } from "react";
import { colors } from "../ui/tokens";

export type ScreenProps = {
  projectId?: string;
  data: import("../api/types").ScreenData;
  selectedId?: string;
  onSelect?: (id: string) => void;
  onOpenDetail?: (id: string) => void;
};

export function OperationalFrame({ title, projectId, children }: { title: string; projectId?: string; children: ReactNode }) {
  return (
    <box flexDirection="column" width="100%" height="100%" padding={1}>
      <box border borderStyle="single" title={title} titleColor={colors.focus} flexDirection="column" padding={1} flexGrow={1}>
        <text fg={colors.muted}>{`Proyecto activo: ${projectId ?? "todos"}`}</text>
        {children}
      </box>
    </box>
  );
}

export function emptyMessage(label: string): string {
  return `${label}: no disponible`;
}
