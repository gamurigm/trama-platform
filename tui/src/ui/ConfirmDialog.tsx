import { useKeyboard } from "@opentui/react";
import { colors } from "./tokens";

type ConfirmDialogProps = {
  action: string;
  target: string;
  consequence: string;
  onConfirm: () => void;
  onCancel: () => void;
};

export function ConfirmDialog({ action, target, consequence, onConfirm, onCancel }: ConfirmDialogProps) {
  useKeyboard((key) => {
    const name = String(key.name).toLowerCase();
    if (name === "y" || name === "enter" || name === "return") onConfirm();
    if (name === "n" || name === "escape" || name === "esc") onCancel();
  });

  return (
    <box
      border
      borderStyle="double"
      title="Confirmar acción"
      titleColor={colors.attention}
      flexDirection="column"
      padding={1}
      width="60%"
    >
      <text><strong>{action}</strong> en {target}</text>
      <text>{consequence}</text>
      <text><span fg={colors.attention}>[y/Enter]</span> confirmar  <span fg={colors.muted}>[n/Esc]</span> cancelar</text>
    </box>
  );
}
