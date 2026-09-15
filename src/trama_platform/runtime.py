"""Runtime local de TRAMA para contratos, pruebas y adaptadores."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import AgentResult, MemoryCandidate, ProjectManifest, PromotionRequest, TaskEnvelope
from .namespaces import can_promote, can_read_candidate
from .ports import CanonicalKnowledgePort, ContextMemoryPort, CoordinationPort


@dataclass
class InMemoryCoordination(CoordinationPort):
    tasks: dict[str, TaskEnvelope] = field(default_factory=dict)
    results: dict[str, AgentResult] = field(default_factory=dict)

    def submit_task(self, task: TaskEnvelope) -> str:
        if task.task_id in self.tasks:
            return task.task_id
        self.tasks[task.task_id] = task
        return task.task_id

    def record_result(self, result: AgentResult) -> None:
        if result.task_id not in self.tasks:
            raise KeyError(f"La tarea {result.task_id} no esta registrada")
        self.results[result.task_id] = result


@dataclass
class InMemoryContextMemory(ContextMemoryPort):
    candidates: dict[str, MemoryCandidate] = field(default_factory=dict)

    def put_candidate(self, candidate: MemoryCandidate) -> str:
        self.candidates[candidate.candidate_id] = candidate
        return candidate.candidate_id

    def get_candidate(self, candidate_id: str) -> MemoryCandidate | None:
        return self.candidates.get(candidate_id)

    def search(self, organization_id: str, project_id: str, query: str) -> list[MemoryCandidate]:
        normalized = query.casefold()
        return [
            candidate
            for candidate in self.candidates.values()
            if can_read_candidate(candidate, organization_id, project_id)
            and normalized in f"{candidate.subject} {candidate.fact}".casefold()
        ]


@dataclass
class InMemoryCanonicalKnowledge(CanonicalKnowledgePort):
    published: dict[str, PromotionRequest] = field(default_factory=dict)

    def publish(self, request: PromotionRequest, candidate: MemoryCandidate) -> str:
        if not can_promote(request, candidate):
            raise PermissionError("La promocion no esta aprobada para el proyecto")
        if candidate.status != "validated":
            raise ValueError("Solo se puede publicar un candidato validado")
        self.published[request.promotion_id] = request
        return request.promotion_id


@dataclass
class ProjectRegistry:
    projects: dict[str, ProjectManifest] = field(default_factory=dict)

    def register(self, manifest: ProjectManifest) -> ProjectManifest:
        existing = self.projects.get(manifest.project_id)
        if existing and existing.model_dump(mode="json") != manifest.model_dump(mode="json"):
            raise ValueError(
                f"El proyecto {manifest.project_id} ya esta registrado con otra configuracion"
            )
        self.projects[manifest.project_id] = manifest
        return manifest

    def get(self, project_id: str) -> ProjectManifest:
        try:
            return self.projects[project_id]
        except KeyError as exc:
            raise KeyError(f"El proyecto {project_id} no esta registrado") from exc


class TramaRuntime:
    """Orquesta el flujo minimo sin acoplarlo a un proveedor externo."""

    def __init__(
        self,
        *,
        coordination: CoordinationPort | None = None,
        context_memory: ContextMemoryPort | None = None,
        canonical_knowledge: CanonicalKnowledgePort | None = None,
    ) -> None:
        self.coordination = coordination or InMemoryCoordination()
        self.context_memory = context_memory or InMemoryContextMemory()
        self.canonical_knowledge = canonical_knowledge or InMemoryCanonicalKnowledge()
        self.projects = ProjectRegistry()
        self.tasks: dict[str, TaskEnvelope] = {}

    def register_project(self, manifest: ProjectManifest) -> ProjectManifest:
        return self.projects.register(manifest)

    def submit_task(self, task: TaskEnvelope) -> str:
        project = self.projects.get(task.project_id)
        if task.organization_id != project.organization_id:
            raise ValueError("La organizacion de la tarea no coincide con el proyecto")
        if task.repository != project.repository:
            raise ValueError("El repositorio de la tarea no coincide con el proyecto")
        existing = self.tasks.get(task.task_id)
        if existing and existing.model_dump(mode="json") != task.model_dump(mode="json"):
            raise ValueError(f"La tarea {task.task_id} ya existe con otra configuracion")
        self.tasks[task.task_id] = task
        return self.coordination.submit_task(task)

    def record_result(self, result: AgentResult) -> None:
        if result.task_id not in self.tasks:
            raise KeyError(f"La tarea {result.task_id} no esta registrada")
        self.coordination.record_result(result)

    def capture_memory(self, candidate: MemoryCandidate) -> str:
        project = self.projects.get(candidate.project_id)
        if candidate.organization_id != project.organization_id:
            raise ValueError("La organizacion de la memoria no coincide con el proyecto")
        return self.context_memory.put_candidate(candidate)

    def search_memory(
        self, organization_id: str, project_id: str, query: str
    ) -> list[MemoryCandidate]:
        project = self.projects.get(project_id)
        if organization_id != project.organization_id:
            raise ValueError("La organizacion de la busqueda no coincide con el proyecto")
        return list(self.context_memory.search(organization_id, project_id, query))

    def promote(self, request: PromotionRequest) -> str:
        candidate = self.context_memory.get_candidate(request.candidate_id)
        if candidate is None:
            raise KeyError(f"El candidato {request.candidate_id} no existe")
        project = self.projects.get(request.project_id)
        if request.organization_id != project.organization_id:
            raise ValueError("La organizacion de la promocion no coincide con el proyecto")
        return self.canonical_knowledge.publish(request, candidate)
