import { useKeyboard } from "@opentui/react";
import { useState } from "react";
import type { ProjectManifest } from "../api/types";
import { colors } from "./tokens";

export function ProjectPicker({ projects, onChoose, onClose }: { projects: ProjectManifest[]; onChoose: (project: ProjectManifest) => void; onClose: () => void }) {
  const [selectedIndex, setSelectedIndex] = useState(0);
  useKeyboard((key) => {
    const name = String(key.name).toLowerCase();
    if (name === "escape" || name === "esc") return onClose();
    if (name === "down" || name === "arrowdown" || name === "j") return setSelectedIndex((current) => projects.length ? (current + 1) % projects.length : 0);
    if (name === "up" || name === "arrowup" || name === "k") return setSelectedIndex((current) => projects.length ? (current - 1 + projects.length) % projects.length : 0);
    if (name === "enter" || name === "return") {
      const project = projects[selectedIndex];
      if (project) onChoose(project);
    }
  });
  return (
    <box position="absolute" top={5} left="20%" right="20%" zIndex={20} backgroundColor={colors.panel} border borderStyle="double" title="Proyecto activo" titleColor={colors.focus} flexDirection="column" padding={1}>
      {projects.length === 0 ? <text fg={colors.muted}>No hay proyectos disponibles</text> : projects.map((project, index) => (
        <text key={project.project_id} wrapMode="none"><span fg={index === selectedIndex ? colors.focus : colors.muted}>{index === selectedIndex ? "› " : "  "}</span>{`${project.project_id} · ${project.repository}`}</text>
      ))}
      <text fg={colors.muted}>↑/↓ o j/k · Enter seleccionar · Esc cerrar</text>
    </box>
  );
}
