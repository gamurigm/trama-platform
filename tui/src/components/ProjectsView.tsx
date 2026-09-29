import { useEffect, useState } from "react";
import { useKeyboard } from "@opentui/react";
import { idField, list, useConsole, useLoad } from "../console";
import { Action, Detail, Hint, RecordList } from "./Primitives";
import { detectedRepository, findDetectedProject } from "../repository";

export function ProjectsView() {
  const { client, locked, form, setProject } = useConsole();
  const loaded = useLoad(() => client.getProjects());
  const [selected, select] = useState(0);
  const projects = loaded.data ?? [];
  const current = projects[selected];
  useEffect(() => {
    const match = findDetectedProject(projects);
    if (match) {
      select(projects.indexOf(match));
      setProject(match);
    }
  }, [projects, setProject]);
  const folderName = detectedRepository.root.replaceAll("\\", "/").split("/").filter(Boolean).at(-1) ?? "";
  const suggestedId = folderName.toLowerCase().replace(/[^a-z0-9._-]+/g, "-").replace(/^[^a-z0-9]+/, "").slice(0, 100) || "proyecto";
  const repositoryHint = detectedRepository.root
    ? `Detectado: ${detectedRepository.root}${detectedRepository.remote ? ` · origin: ${detectedRepository.remote}` : ""}`
    : "Ruta absoluta o URL del repositorio";
  const create = () => form({ title: "Registrar proyecto", description: detectedRepository.root
      ? "TRAMA detectó el repositorio desde el directorio actual. Revisa los datos y confirma el registro."
      : "Define el repositorio y el contexto de trabajo para sus requisitos y tareas.",
    fields: [
      { ...idField("project_id", "ID del proyecto"), initial: detectedRepository.root ? suggestedId : "",
        validate: (value) => /^[a-z0-9][a-z0-9._-]{0,99}$/.test(value) ? undefined : "Usa minúsculas, números, puntos o guiones" },
      { name: "organization_id", label: "Organización", initial: "default", required: true },
      { name: "repository", label: "Repositorio", hint: repositoryHint, initial: detectedRepository.root, required: true },
      { name: "default_branch", label: "Rama detectada", initial: detectedRepository.branch || "main", required: true },
      { name: "capabilities", label: "Capacidades", hint: "Separadas por comas; por ejemplo: frontend, api, docs" },
      { name: "commands", label: "Comandos del proyecto", multiline: true, hint: "Uno por línea: nombre=comando. Se registran sin ejecutarlos.",
        validate: (value) => value.split("\n").filter(Boolean).every((line) => /^\s*[^=\s]+\s*=\s*.+$/.test(line)) ? undefined : "Usa nombre=comando en cada línea" },
    ], onSubmit: async (v) => {
      const commands = Object.fromEntries(v.commands!.split("\n").filter((line) => line.trim()).map((line) => {
        const equal = line.indexOf("="); return [line.slice(0, equal).trim(), line.slice(equal + 1).trim()];
      }));
      const project = await client.registerProject({ project_id: v.project_id!, organization_id: v.organization_id!, repository: v.repository!,
        default_branch: v.default_branch!, capabilities: list(v.capabilities!), commands });
      setProject(project);
    } });
  useKeyboard((key) => { if (!locked && key.name === "n") create(); });
  return <box flexDirection="column" flexGrow={1} gap={1} minHeight={0}>
    <box flexDirection="row" gap={2}><Action label="N Nuevo proyecto" onPress={create} /><Hint>{detectedRepository.root ? `Repositorio detectado: ${detectedRepository.root}` : "↑ ↓ Seleccionar · Enter Activar proyecto"}</Hint></box>
    <RecordList title="Proyectos" loading={loaded.loading} error={loaded.error} selected={selected} onSelect={select}
      rows={projects.map((p) => ({ id: p.project_id, name: p.project_id, description: `${p.organization_id} / ${p.default_branch}` }))}
      onOpen={(i) => { if (projects[i]) setProject(projects[i]!); }}>
      {current && <><Detail values={[["Proyecto", current.project_id], ["Organización", current.organization_id], ["Repositorio", current.repository],
        ["Rama", current.default_branch], ["Capacidades", current.capabilities], ["Comandos", Object.entries(current.commands ?? {}).map(([k, v]) => `${k} = ${v}`)]]} />
        <Action label="Usar este proyecto →" onPress={() => setProject(current)} /></>}
    </RecordList>
  </box>;
}
