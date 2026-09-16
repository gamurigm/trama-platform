import { Panel } from "../ui/Panel";
import type { ProjectManifest } from "../api/types";
import { OperationalFrame, type ScreenProps } from "./OperationalFrame";

export function ProjectsScreen({ projectId, data, selectedId, onSelect }: ScreenProps) {
  const projects = data.projects ?? [];
  return (
    <OperationalFrame title="Projects" projectId={projectId}>
      <Panel title="Proyectos registrados" accent="focus">
        {projects.length === 0 ? <text>no hay proyectos</text> : projects.map((project: ProjectManifest) => (
          <text key={project.project_id} wrapMode="none" onMouseUp={() => onSelect?.(project.project_id)}>
            {`${selectedId === project.project_id ? "›" : " "} ${project.project_id}  ${project.repository}`}
          </text>
        ))}
      </Panel>
    </OperationalFrame>
  );
}
