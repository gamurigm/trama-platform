import type { Project } from "./api/types";

export type DetectedRepository = { root: string; branch: string; remote: string };

export const detectedRepository: DetectedRepository = {
  root: process.env.TRAMA_REPOSITORY_ROOT ?? "",
  branch: process.env.TRAMA_REPOSITORY_BRANCH ?? "",
  remote: process.env.TRAMA_REPOSITORY_REMOTE ?? "",
};

function normalized(value: string) {
  const clean = value.trim().replaceAll("\\", "/").replace(/\/+$/, "").replace(/\.git$/i, "");
  if (/^[a-z]:\//i.test(clean)) return clean.toLowerCase();
  if (/^[a-z][a-z\d+.-]*:\/\//i.test(clean)) {
    try {
      const url = new URL(clean);
      return `${url.host}${url.pathname}`.replace(/\/+$/, "").toLowerCase();
    } catch {}
  }
  const withoutUser = clean.replace(/^.*@(?=[^/]+:)/, "");
  const scp = withoutUser.match(/^([^/:]+):(.+)$/);
  return (scp ? `${scp[1]}/${scp[2]}` : withoutUser).toLowerCase();
}

export function findDetectedProject(projects: Project[]) {
  const identities = [detectedRepository.root, detectedRepository.remote].filter(Boolean).map(normalized);
  return projects.find((project) => identities.includes(normalized(project.repository)));
}
