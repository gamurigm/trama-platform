import { useRef, useState } from "react";
import { useKeyboard, usePaste } from "@opentui/react";
import type { TextareaRenderable } from "@opentui/core";
import type { FormSpec } from "../console";
import { clean, theme } from "../theme";
import { Action, Hint, Panel } from "./Primitives";

export function FormFields({ spec, onClose, onSuccess }: { spec: FormSpec; onClose: () => void; onSuccess: () => void }) {
  const [values, setValues] = useState<Record<string, string>>(() => Object.fromEntries(spec.fields.map((field) => [field.name, field.initial ?? ""])));
  const [step, setStep] = useState(0);
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const pending = useRef(false);
  const textarea = useRef<TextareaRenderable>(null);
  const field = spec.fields[step];
  const update = (value: string) => field && setValues((old) => ({ ...old, [field.name]: value }));
  const next = (fresh?: string) => {
    if (saving) return;
    if (field) {
      const value = fresh ?? values[field.name] ?? "";
      const invalid = field.required && !value.trim() ? "Este campo es obligatorio" : field.validate?.(value);
      if (invalid) { setError(invalid); return; }
      if (fresh !== undefined) update(fresh);
    }
    setError(""); setStep(Math.min(spec.fields.length, step + 1));
  };
  const save = async () => {
    if (pending.current) return;
    pending.current = true; setSaving(true); setError("");
    try { await spec.onSubmit(values); onSuccess(); }
    catch (error) { setError(error instanceof Error ? error.message : "No se pudo guardar. Reintenta."); }
    finally { pending.current = false; setSaving(false); }
  };
  usePaste((event) => {
    if (!field?.secret || saving) return;
    event.preventDefault(); event.stopPropagation();
    const pasted = new TextDecoder().decode(event.bytes).replace(/[\r\n]/g, "");
    setValues((old) => ({ ...old, [field.name]: ((old[field.name] ?? "") + pasted).slice(0, 2000) }));
  });
  useKeyboard((key) => {
    if (saving) { key.preventDefault(); return; }
    if (key.name === "escape") { key.preventDefault(); onClose(); return; }
    if (!field && key.name === "tab") { key.preventDefault(); void save(); return; }
    if (key.name === "tab") {
      key.preventDefault();
      if (key.shift) { setStep((old) => Math.max(0, old - 1)); setError(""); }
      else next();
      return;
    }
    if (field?.multiline && key.name === "return") { key.preventDefault(); next(); return; }
    if (field?.secret) {
      key.preventDefault();
      if (key.name === "backspace") update(Array.from(values[field.name] ?? "").slice(0, -1).join(""));
      else if (key.ctrl && key.name === "u") update("");
      else if (!key.ctrl && !key.meta && key.sequence && !/[\u0000-\u001f\u007f]/.test(key.sequence)) {
        const typed = key.sequence;
        setValues((old) => ({ ...old, [field.name]: ((old[field.name] ?? "") + typed).slice(0, 2000) }));
      }
    }
  });
  return <Panel title={spec.title}>
    <box padding={1} gap={1} flexDirection="column" flexGrow={1}>
      <Hint>{spec.description}</Hint>
      <text fg={theme.violet}>{"━".repeat(Math.min(step + 1, spec.fields.length + 1))}{"─".repeat(Math.max(0, spec.fields.length - step))}  {field ? `PASO ${step + 1} / ${spec.fields.length}` : "REVISAR Y CONFIRMAR"}</text>
      {field ? <box flexDirection="column" gap={1}>
        <text fg={theme.text}><b>{field.label}{field.required ? " *" : ""}</b></text>
        <Hint>{field.hint ?? "Tab para continuar · Shift+Tab para volver"}</Hint>
        <box border borderStyle="rounded" borderColor={theme.violet} paddingX={1}>
          {field.secret ? <text fg={theme.text}>{"•".repeat(Math.min(40, (values[field.name] ?? "").length)) || "Introduce la credencial"} ▌</text>
            : field.multiline ? <textarea key={field.name} ref={textarea} focused={!saving} height={5} width="100%"
                initialValue={values[field.name]} onContentChange={() => update(textarea.current?.plainText ?? "")}
                textColor={theme.text} backgroundColor={theme.panel} focusedBackgroundColor={theme.panel} />
            : <input key={field.name} focused={!saving} value={values[field.name]} maxLength={2000}
                onInput={update} onSubmit={(value) => next(typeof value === "string" ? value : undefined)} textColor={theme.text}
                backgroundColor={theme.panel} focusedBackgroundColor={theme.panel} />}
        </box>
      </box> : <scrollbox flexGrow={1} minHeight={3}>
        {spec.fields.map((item) => <box key={item.name} flexDirection="column" marginBottom={1}>
          <text fg={theme.muted}>{item.label}</text><text fg={theme.text}>{item.secret ? "•••••••• (protegido)" : clean(values[item.name] || "—")}</text>
        </box>)}
      </scrollbox>}
      {error && <text fg={theme.coral}>{clean(error)}</text>}
      <box flexDirection="row" gap={1}>
        <Action label={saving ? "Guardando…" : field ? "Continuar →" : spec.submitLabel ?? "Confirmar"} onPress={() => field ? next() : void save()} />
        <Action label="← Volver" onPress={() => { if (!saving) setStep((old) => Math.max(0, old - 1)); }} />
        <Action label="Esc Cancelar" onPress={() => { if (!saving) onClose(); }} />
      </box>
    </box>
  </Panel>;
}
