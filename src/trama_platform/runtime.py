"""Runtime local de TRAMA para contratos, pruebas y adaptadores."""

from __future__ import annotations

from dataclasses import dataclass, field

from .contracts import (
    AgentResult,
    MemoryCandidate,
    OperationEvent,
    ProjectManifest,
    PromotionRequest,
    TaskEnvelope,
)
from .namespaces import can_promote, can_read_candidate
from .ports import CanonicalKnowledgePort, ContextMemoryPort, CoordinationPort, StateStorePort


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
        state_store: StateStorePort | None = None,
    ) -> None:
        self.coordination = coordination or InMemoryCoordination()
        self.context_memory = context_memory or InMemoryContextMemory()
        self.canonical_knowledge = canonical_knowledge or InMemoryCanonicalKnowledge()
        self.state_store = state_store
        self.projects = ProjectRegistry()
        self.tasks: dict[str, TaskEnvelope] = {}
        self._events: list[OperationEvent] = []

        if self.state_store is not None:
            self.projects.projects.update(
                {project.project_id: project for project in self.state_store.load_projects()}
            )
            self.tasks.update({task.task_id: task for task in self.state_store.load_tasks()})
            if isinstance(self.coordination, InMemoryCoordination):
                self.coordination.tasks.update(self.tasks)
                self.coordination.results.update(
                    {result.task_id: result for result in self.state_store.load_results()}
                )
            if isinstance(self.context_memory, InMemoryContextMemory):
                self.context_memory.candidates.update(
                    {
                        candidate.candidate_id: candidate
                        for candidate in self.state_store.load_candidates()
                    }
                )
            if isinstance(self.canonical_knowledge, InMemoryCanonicalKnowledge):
                self.canonical_knowledge.published.update(
                    {
                        promotion.promotion_id: promotion
                        for promotion in self.state_store.load_promotions()
                    }
                )

    def _record_event(
        self,
        *,
        action: str,
        status: str,
        organization_id: str = "default",
        project_id: str | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        event = OperationEvent(
            actor="trama",
            action=action,
            status=status,
            organization_id=organization_id,
            project_id=project_id,
            details=details or {},
        )
        if self.state_store is not None:
            self.state_store.append_event(event)
        else:
            self._events.append(event)

    def register_project(self, manifest: ProjectManifest) -> ProjectManifest:
        project = self.projects.register(manifest)
        if self.state_store is not None:
            self.state_store.save_project(project)
        self._record_event(
            action="project.register",
            status="accepted",
            organization_id=project.organization_id,
            project_id=project.project_id,
        )
        return project

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
        task_id = self.coordination.submit_task(task)
        if self.state_store is not None:
            self.state_store.save_task(task)
        self._record_event(
            action="task.submit",
            status="accepted",
            organization_id=task.organization_id,
            project_id=task.project_id,
            details={"task_id": task.task_id},
        )
        return task_id

    def record_result(self, result: AgentResult) -> None:
        if result.task_id not in self.tasks:
            raise KeyError(f"La tarea {result.task_id} no esta registrada")
        self.coordination.record_result(result)
        updated_task = self.tasks[result.task_id].model_copy(
            update={"state": result.status}
        )
        self.tasks[result.task_id] = updated_task
        if isinstance(self.coordination, InMemoryCoordination):
            self.coordination.tasks[result.task_id] = updated_task
        if self.state_store is not None:
            self.state_store.save_task(updated_task)
            self.state_store.save_result(result)
        task = updated_task
        self._record_event(
            action="task.result",
            status="succeeded" if result.status == "succeeded" else "failed",
            organization_id=task.organization_id,
            project_id=task.project_id,
            details={"task_id": result.task_id, "result_status": result.status},
        )

    def capture_memory(self, candidate: MemoryCandidate) -> str:
        project = self.projects.get(candidate.project_id)
        if candidate.organization_id != project.organization_id:
            raise ValueError("La organizacion de la memoria no coincide con el proyecto")
        candidate_id = self.context_memory.put_candidate(candidate)
        if self.state_store is not None:
            self.state_store.save_candidate(candidate)
        self._record_event(
            action="memory.capture",
            status="accepted",
            organization_id=candidate.organization_id,
            project_id=candidate.project_id,
            details={"candidate_id": candidate.candidate_id},
        )
        return candidate_id

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
        promotion_id = self.canonical_knowledge.publish(request, candidate)
        if self.state_store is not None:
            self.state_store.save_promotion(request)
        self._record_event(
            action="knowledge.promote",
            status="succeeded",
            organization_id=request.organization_id,
            project_id=request.project_id,
            details={"promotion_id": promotion_id, "candidate_id": request.candidate_id},
        )
        return promotion_id

    def list_projects(self) -> list[ProjectManifest]:
        return list(self.projects.projects.values())

    def get_project(self, project_id: str) -> ProjectManifest:
        return self.projects.get(project_id)

    def list_tasks(self) -> list[TaskEnvelope]:
        return list(self.tasks.values())

    def get_task(self, task_id: str) -> TaskEnvelope:
        try:
            return self.tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"La tarea {task_id} no esta registrada") from exc

    def cancel_task(self, task_id: str) -> TaskEnvelope:
        task = self.get_task(task_id)
        if task.state not in {"accepted", "running", "blocked"}:
            raise ValueError(f"La tarea {task_id} no se puede cancelar desde {task.state}")
        updated = task.model_copy(update={"state": "cancelled"})
        self.tasks[task_id] = updated
        if isinstance(self.coordination, InMemoryCoordination):
            self.coordination.tasks[task_id] = updated
        if self.state_store is not None:
            self.state_store.save_task(updated)
        self._record_event(
            action="task.cancel",
            status="accepted",
            organization_id=updated.organization_id,
            project_id=updated.project_id,
            details={"task_id": task_id},
        )
        return updated

    def retry_task(self, task_id: str) -> TaskEnvelope:
        task = self.get_task(task_id)
        if task.state not in {"failed", "partial", "blocked", "cancelled"}:
            raise ValueError(f"La tarea {task_id} no se puede reintentar desde {task.state}")
        updated = task.model_copy(update={"state": "accepted"})
        self.tasks[task_id] = updated
        if isinstance(self.coordination, InMemoryCoordination):
            self.coordination.tasks[task_id] = updated
        if self.state_store is not None:
            self.state_store.save_task(updated)
        self._record_event(
            action="task.retry",
            status="accepted",
            organization_id=updated.organization_id,
            project_id=updated.project_id,
            details={"task_id": task_id},
        )
        return updated

    def list_agents(self) -> list[dict[str, object]]:
        agents: dict[str, dict[str, object]] = {}
        for task in self.tasks.values():
            agent = agents.setdefault(
                task.actor,
                {"agent_id": task.actor, "tasks": 0, "projects": set()},
            )
            agent["tasks"] = int(agent["tasks"]) + 1
            projects = agent["projects"]
            if isinstance(projects, set):
                projects.add(task.project_id)
        return [
            {
                "agent_id": agent["agent_id"],
                "tasks": agent["tasks"],
                "projects": sorted(agent["projects"]),
            }
            for agent in sorted(agents.values(), key=lambda item: str(item["agent_id"]))
        ]

    def list_memory_candidates(
        self, organization_id: str, project_id: str
    ) -> list[MemoryCandidate]:
        project = self.projects.get(project_id)
        if organization_id != project.organization_id:
            raise ValueError("La organizacion de la memoria no coincide con el proyecto")
        candidates = getattr(self.context_memory, "candidates", {}).values()
        return [
            candidate
            for candidate in candidates
            if can_read_candidate(candidate, organization_id, project_id)
        ]

    def list_events(self, limit: int = 100) -> list[OperationEvent]:
        if self.state_store is not None:
            return list(self.state_store.list_events(limit))
        return self._events[-max(1, min(limit, 1000)) :]

    def status(self) -> dict[str, object]:
        if self.state_store is not None:
            candidates = self.state_store.count("candidate")
            results = self.state_store.count("result")
            events = self.state_store.count_events()
        else:
            candidates = len(getattr(self.context_memory, "candidates", {}))
            results = len(getattr(self.coordination, "results", {}))
            events = len(self._events)
        return {
            "service": "trama",
            "status": "ready",
            "projects": len(self.projects.projects),
            "tasks": len(self.tasks),
            "results": results,
            "coordination": type(self.coordination).__name__,
            "memory_candidates": candidates,
            "events": events,
        }
