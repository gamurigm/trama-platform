import { useEffect, useRef, type ReactNode } from "react";
import { useKeyboard, useTerminalDimensions } from "@opentui/react";
import type { ScrollBoxRenderable } from "@opentui/core";
import { useConsole } from "../console";
import { clean, theme } from "../theme";

export function Panel({ title, children, grow = 1 }: { title: string; children: ReactNode; grow?: number }) {
  return <box border borderStyle="rounded" borderColor={theme.border} title={` ${title} `}
    backgroundColor={theme.panel} flexDirection="column" paddingX={1} paddingY={0} flexGrow={grow} minHeight={3}>{children}</box>;
}
export function Hint({ children }: { children: ReactNode }) { return <text fg={theme.muted}>{children}</text>; }
export function Action({ label, onPress }: { label: string; onPress: () => void }) {
  return <box backgroundColor={theme.raised} paddingX={1} onMouseDown={onPress}><text fg={theme.cyan}>{label}</text></box>;
}
export function LoadState({ loading, error, empty, noun = "elementos" }: { loading: boolean; error?: string; empty?: boolean; noun?: string }) {
  if (error) return <text fg={theme.coral}>No se pudo cargar: {clean(error)} · R reintenta</text>;
  if (loading) return <text fg={theme.cyan}>◌ Cargando {noun}…</text>;
  if (empty) return <box flexDirection="column" paddingY={1}><text fg={theme.text}>Todavía no hay {noun}.</text><Hint>Usa las acciones de esta vista para comenzar.</Hint></box>;
  return null;
}
export function RecordList({ title, rows, selected, onSelect, onOpen, children, loading = false, error }: {
  title: string; rows: { id: string; name: string; description: string }[]; selected: number;
  onSelect: (index: number) => void; onOpen?: (index: number) => void; children?: ReactNode;
  loading?: boolean; error?: string;
}) {
  const { locked } = useConsole();
  const { width, height } = useTerminalDimensions();
  const detail = useRef<ScrollBoxRenderable>(null);
  useEffect(() => { detail.current?.scrollTo(0); }, [selected]);
  useKeyboard((key) => {
    if (!locked && ["pagedown", "pageup"].includes(key.name)) {
      key.preventDefault(); detail.current?.scrollBy(key.name === "pagedown" ? 6 : -6);
    }
  });
  const narrow = width < 88;
  return <box flexDirection={narrow ? "column" : "row"} flexGrow={1} gap={1} minHeight={0}>
    <box width={narrow ? "100%" : "43%"} height={narrow ? Math.max(5, Math.floor((height - 10) / 2)) : undefined} flexShrink={0}>
      <Panel title={`${title} · ${rows.length}`}>
        <LoadState loading={loading} error={error} empty={!rows.length} noun={title.toLowerCase()} />
        {rows.length > 0 && <select focused={!locked} flexGrow={1} minHeight={2}
          options={rows.map((row) => ({ name: clean(row.name), description: clean(row.description), value: row.id }))}
          selectedIndex={Math.min(selected, rows.length - 1)} onChange={(i) => onSelect(i)} onSelect={(i) => onOpen?.(i)}
          backgroundColor={theme.panel} focusedBackgroundColor={theme.panel} textColor={theme.text}
          focusedTextColor={theme.text} descriptionColor={theme.muted} selectedBackgroundColor={theme.selected}
          selectedTextColor={theme.cyan} selectedDescriptionColor={theme.text} showScrollIndicator />}
      </Panel>
    </box>
    <Panel title="Detalle"><scrollbox ref={detail} flexGrow={1} minHeight={0}>{children ?? <Hint>Selecciona un elemento con ↑ ↓.</Hint>}</scrollbox><Hint>PgUp / PgDn Desplazar detalle</Hint></Panel>
  </box>;
}
export function Detail({ values }: { values: [string, unknown][] }) {
  return <box flexDirection="column" gap={1} paddingY={1}>{values.map(([label, value]) =>
    <box key={label} flexDirection="column"><text fg={theme.muted}>{label.toUpperCase()}</text>
      <text fg={theme.text}>{clean(Array.isArray(value) ? value.join(" · ") || "—" : value)}</text></box>)}</box>;
}
