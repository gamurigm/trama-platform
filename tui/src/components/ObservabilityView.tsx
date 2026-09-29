import { useState } from "react";
import { useKeyboard } from "@opentui/react";
import type { LogFilters } from "../api/types";
import { useConsole, useLoad } from "../console";
import { Action, Detail, Hint, RecordList } from "./Primitives";

export function ObservabilityView() {
  const { client, locked, form, project } = useConsole();
  const [filters, setFilters] = useState<LogFilters>({});
  const [selected, select] = useState(0);
  const loaded = useLoad(() => client.getLogs({ project_id: project?.project_id, ...filters }), [project?.project_id, JSON.stringify(filters)]);
  const logs = loaded.data ?? [];
  const current = logs[selected];
  const filter = () => form({ title: "Filtrar actividad", description: "Deja un campo vacío para incluir todos sus valores. Se muestran los últimos 100 registros.",
    fields: [["project_id", "Proyecto"], ["requirement_id", "Requisito"], ["phase_id", "Fase"], ["task_id", "Tarea"], ["level", "Nivel"]].map(([name, label]) => ({
      name: name!, label: label!, initial: filters[name as keyof LogFilters] ?? (name === "project_id" ? project?.project_id : ""),
      hint: name === "level" ? "debug · info · warning · error (o vacío)" : undefined,
    })), onSubmit: async (values) => {
      if (values.level && !["debug", "info", "warning", "error"].includes(values.level)) throw new Error("Nivel de log no válido");
      setFilters(values); select(0);
    }, submitLabel: "Aplicar filtros" });
  useKeyboard((key) => { if (!locked && key.name === "f") filter(); });
  return <box flexDirection="column" flexGrow={1} gap={1} minHeight={0}>
    <box flexDirection="row" gap={2}><Action label="F Filtrar actividad" onPress={filter} /><Hint>Logs saneados · correlación de extremo a extremo</Hint></box>
    <RecordList title="Actividad" selected={selected} onSelect={select} loading={loaded.loading} error={loaded.error}
      rows={logs.map((x) => ({ id: x.log_id, name: `${x.level.toUpperCase()} · ${x.message}`, description: `${x.created_at} · ${x.actor}` }))}>
      {current && <Detail values={[["Mensaje", current.message], ["Nivel", current.level], ["Agente", current.actor], ["Momento", current.created_at],
        ["Proyecto", current.project_id], ["Tarea", current.task_id], ["Fase", current.phase_id], ["Correlación", current.correlation_id]]} />}
    </RecordList>
  </box>;
}
