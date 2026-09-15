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

    def search(self, project_id: str, query: str) -> list[MemoryCandidate]:
        normalized = query.casefold()
        return [
            candidate
            for candidate in self.candidates.values()
            if can_read_candidate(candidate, project_id)
            and normalized in f"{candidate.subject} {candidate.fact}".casefold()
        ]


@dataclass
class InMemoryCanonicalKnowledge(CanonicalKnowledgePort):
    published: dict[str, PromotionRequest] = field(default_factory=dict)

    def publish(self, request: PromotionRequest, candidate: MemoryCandidate) -> str:
        if not can_promote(request, candidate.project_id):
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

    def register_project(self, manifest: ProjectManifest) -> ProjectManifest:
        return self.projects.register(manifest)

    def submit_task(self, task: TaskEnvelope) -> str:
        if task.project_id not in self.projects.projects:
            raise KeyError(f"El proyecto {task.project_id} no esta registrado")
        return self.coordination.submit_task(task)

    def record_result(self, result: AgentResult) -> None:
        self.coordination.record_result(result)

    def capture_memory(self, candidate: MemoryCandidate) -> str:
        if candidate.project_id not in self.projects.projects:
            raise KeyError(f"El proyecto {candidate.project_id} no esta registrado")
        return self.context_memory.put_candidate(candidate)

    def promote(self, request: PromotionRequest) -> str:
        candidate = self.context_memory.get_candidate(request.candidate_id)
        if candidate is None:
            raise KeyError(f"El candidato {request.candidate_id} no existe")
        return self.canonical_knowledge.publish(request, candidate)
