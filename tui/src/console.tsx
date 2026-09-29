import { createContext, useContext, useEffect, useState } from "react";
import type { TramaApiClient } from "./api/client";
import type { Project } from "./api/types";

export type Field = { name: string; label: string; hint?: string; initial?: string; required?: boolean;
  multiline?: boolean; secret?: boolean; validate?: (value: string) => string | undefined };
export type FormSpec = { title: string; description: string; fields: Field[]; submitLabel?: string;
  onSubmit: (values: Record<string, string>) => Promise<unknown> };
export type ConsoleState = { client: TramaApiClient; version: number; locked: boolean;
  project?: Project; setProject: (project: Project) => void; form: (spec: FormSpec) => void;
  inspect: (title: string, rows: string[]) => void;
  run: (operation: () => Promise<unknown>, success: string) => Promise<void>; refresh: () => void };
export const ConsoleContext = createContext<ConsoleState>(null!);
export const useConsole = () => useContext(ConsoleContext);

export function useLoad<T>(load: () => Promise<T>, dependencies: unknown[] = []) {
  const { version } = useConsole();
  const [state, setState] = useState<{ data?: T; error?: string; loading: boolean }>({ loading: true });
  useEffect(() => {
    let alive = true;
    setState((old) => ({ ...old, loading: true, error: undefined }));
    load().then((data) => { if (alive) setState({ data, loading: false }); },
      (error) => { if (alive) setState((old) => ({ ...old, loading: false, error: error.message ?? "No se pudo cargar" })); });
    return () => { alive = false; };
  }, [version, ...dependencies]);
  return state;
}

export const list = (value: string) => value.split(/[\n,]/).map((item) => item.trim()).filter(Boolean);
export const criteria = (value: string) => value.split("\n").map((item) => item.trim()).filter(Boolean);
export const idField = (name: string, label: string): Field => ({ name, label, required: true,
  hint: "Letras, números, puntos, guiones y dos puntos. Sin espacios.",
  validate: (value) => /^[A-Za-z0-9][A-Za-z0-9._:-]{0,99}$/.test(value) ? undefined : "Usa un ID válido de hasta 100 caracteres" });
export const acceptanceField: Field = { name: "acceptance_criteria", label: "Criterios de aceptación", multiline: true,
  required: true, hint: "Un resultado verificable por línea. Ctrl+Enter o Tab para continuar." };
