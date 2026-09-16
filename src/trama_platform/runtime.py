"""Runtime local de TRAMA para contratos, pruebas y adaptadores."""

from __future__ import annotations

from dataclasses import dataclass, field
from threading import RLock

from .contracts import (
    AgentResult,
    MemoryCandidate,
    OperationEvent,
    PlanProposal,
    ProjectManifest,
    ProjectPhase,
    PromotionRequest,
    Requirement,
    TaskEnvelope,
    TaskLog,
    TimelineEntry,
)
from .namespaces import can_promote, can_read_candidate
from .observability import sanitize_message
from .ports import CanonicalKnowledgePort, ContextMemoryPort, CoordinationPort, StateStorePort
from .queueing import TaskDispatcher


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

    def search(
        self, organization_id: str, project_id: str, query: str, agent_id: str | None = None
    ) -> list[MemoryCandidate]:
        normalized = query.casefold()
        return [
            candidate
            for candidate in self.candidates.values()
            if can_read_candidate(candidate, organization_id, project_id, agent_id)
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
        queue_capacity: int = 100,
        max_concurrency: int = 4,
        dispatch_timeout_seconds: int = 900,
    ) -> None:
        self.coordination = coordination or InMemoryCoordination()
        self.context_memory = context_memory or InMemoryContextMemory()
        self.canonical_knowledge = canonical_knowledge or InMemoryCanonicalKnowledge()
        self.state_store = state_store
        self.projects = ProjectRegistry()
        self.requirements: dict[str, Requirement] = {}
        self.phases: dict[str, ProjectPhase] = {}
        self.tasks: dict[str, TaskEnvelope] = {}
        self.proposals: dict[str, PlanProposal] = {}
        self._events: list[OperationEvent] = []
        self._logs: list[TaskLog] = []
        self._task_lock = RLock()

        if self.state_store is not None:
            self.projects.projects.update(
                {project.project_id: project for project in self.state_store.load_projects()}
            )
            self.requirements.update(
                {item.requirement_id: item for item in self.state_store.load_requirements()}
            )
            self.proposals.update(
                {item.proposal_id: item for item in self.state_store.load_plan_proposals()}
            )
            self.phases.update({item.phase_id: item for item in self.state_store.load_phases()})
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

        recovered_tasks: list[TaskEnvelope] = []
        for task in self.tasks.values():
            if task.state == "running":
                normalized = task.model_copy(update={"state": "accepted"})
                self.tasks[task.task_id] = normalized
                if self.state_store is not None:
                    self.state_store.save_task(normalized)
                recovered_tasks.append(normalized)
            elif task.state == "accepted":
                recovered_tasks.append(task)

        self.dispatcher = TaskDispatcher(
            self.coordination,
            queue_capacity=queue_capacity,
            max_concurrency=max_concurrency,
            dispatch_timeout_seconds=dispatch_timeout_seconds,
            transition=self._transition_task,
            current_task=self.tasks.get,
        )
        self.dispatcher.recover(recovered_tasks)
        self._refresh_planning_state()

    def _record_event(
        self,
        *,
        action: str,
        status: str,
        organization_id: str = "default",
        project_id: str | None = None,
        requirement_id: str | None = None,
        phase_id: str | None = None,
        task_id: str | None = None,
        correlation_id: str | None = None,
        duration_ms: int | None = None,
        details: dict[str, object] | None = None,
    ) -> None:
        event = OperationEvent(
            actor="trama",
            action=action,
            status=status,
            organization_id=organization_id,
            project_id=project_id,
            requirement_id=requirement_id,
            phase_id=phase_id,
            task_id=task_id,
            correlation_id=correlation_id,
            duration_ms=duration_ms,
            details=details or {},
        )
        if self.state_store is not None:
            self.state_store.append_event(event)
        else:
            self._events.append(event)

    def _transition_task(
        self,
        task: TaskEnvelope,
        action: str,
        event_status: str,
        details: dict[str, object],
    ) -> None:
        event = OperationEvent(
            actor="trama",
            action=action,
            status=event_status,
            organization_id=task.organization_id,
            project_id=task.project_id,
            requirement_id=task.requirement_id,
            phase_id=task.phase_id,
            task_id=task.task_id,
            correlation_id=task.correlation_id or f"task:{task.task_id}",
            details=details,
        )
        if self.state_store is not None:
            self.state_store.save_task_transition(task, event)
        else:
            self._events.append(event)
        self._record_task_log(
            task=task,
            level="info" if event_status == "accepted" else "error",
            message=action,
            metadata=details,
        )
        with self._task_lock:
            self.tasks[task.task_id] = task
            if isinstance(self.coordination, InMemoryCoordination):
                self.coordination.tasks[task.task_id] = task
        self._refresh_planning_state()

    def _persist_task_acceptance(self, task: TaskEnvelope, *, action: str = "task.submit") -> None:
        event = OperationEvent(
            actor="trama",
            action=action,
            status="accepted",
            organization_id=task.organization_id,
            project_id=task.project_id,
            requirement_id=task.requirement_id,
            phase_id=task.phase_id,
            task_id=task.task_id,
            correlation_id=task.correlation_id or f"task:{task.task_id}",
            details={"task_id": task.task_id},
        )
        if self.state_store is not None:
            self.state_store.save_task_transition(task, event)
        else:
            self._events.append(event)
        self._record_task_log(
            task=task,
            level="info",
            message=action,
            metadata={"task_id": task.task_id},
        )
        with self._task_lock:
            self.tasks[task.task_id] = task
            if isinstance(self.coordination, InMemoryCoordination):
                self.coordination.tasks[task.task_id] = task

    def _phase_dependencies_complete(self, phase: ProjectPhase) -> bool:
        return all(
            self.phases.get(dependency) is not None
            and self.phases[dependency].status == "completed"
            for dependency in phase.depends_on
        )

    def _task_ready_for_dispatch(self, task: TaskEnvelope) -> bool:
        if task.phase_id is not None:
            phase = self.phases.get(task.phase_id)
            if phase is None or phase.status not in {"ready", "in_progress"}:
                return False
        return all(
            self.tasks.get(dependency) is not None
            and self.tasks[dependency].state == "succeeded"
            for dependency in task.depends_on
        )

    def _refresh_planning_state(self) -> None:
        changed = True
        while changed:
            changed = False
            for phase in list(self.phases.values()):
                phase_tasks = [
                    task for task in self.tasks.values() if task.phase_id == phase.phase_id
                ]
                if phase_tasks and all(task.state == "succeeded" for task in phase_tasks):
                    desired = "completed"
                elif any(task.state in {"failed", "blocked"} for task in phase_tasks):
                    desired = "blocked"
                elif any(task.state in {"accepted", "running"} for task in phase_tasks):
                    desired = "in_progress"
                elif phase.approved_by and self._phase_dependencies_complete(phase):
                    desired = "ready"
                else:
                    desired = phase.status
                if desired != phase.status:
                    updated = phase.model_copy(update={"status": desired})
                    self.phases[phase.phase_id] = updated
                    if self.state_store is not None:
                        self.state_store.save_phase(updated)
                    changed = True
            for requirement in list(self.requirements.values()):
                requirement_phases = [
                    phase
                    for phase in self.phases.values()
                    if phase.requirement_id == requirement.requirement_id
                ]
                if requirement_phases and all(
                    phase.status == "completed" for phase in requirement_phases
                ):
                    desired = "completed"
                elif any(phase.status == "blocked" for phase in requirement_phases):
                    desired = "blocked"
                elif any(phase.status in {"ready", "in_progress"} for phase in requirement_phases):
                    desired = "in_progress"
                elif any(phase.approved_by for phase in requirement_phases):
                    desired = "approved"
                else:
                    desired = requirement.status
                if desired != requirement.status:
                    updated = requirement.model_copy(update={"status": desired})
                    self.requirements[requirement.requirement_id] = updated
                    if self.state_store is not None:
                        self.state_store.save_requirement(updated)
                    changed = True
            for task in list(self.tasks.values()):
                if (
                    task.state == "planned"
                    and task.approved_by
                    and self._task_ready_for_dispatch(task)
                ):
                    updated = task.model_copy(update={"state": "accepted"})
                    self.tasks[task.task_id] = updated
                    self.dispatcher.submit(
                        updated,
                        persist=lambda item=updated: self._persist_task_acceptance(
                            item, action="task.approve"
                        ),
                    )
                    changed = True

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

    def register_requirement(self, requirement: Requirement) -> Requirement:
        project = self.projects.get(requirement.project_id)
        if requirement.organization_id != project.organization_id:
            raise ValueError("La organizacion del requisito no coincide con el proyecto")
        existing = self.requirements.get(requirement.requirement_id)
        if existing and existing.model_dump(mode="json") != requirement.model_dump(mode="json"):
            raise ValueError(
                f"El requisito {requirement.requirement_id} ya esta registrado "
                "con otra configuracion"
            )
        self.requirements[requirement.requirement_id] = requirement
        if self.state_store is not None:
            self.state_store.save_requirement(requirement)
        self._record_event(
            action="requirement.register",
            status="accepted",
            organization_id=requirement.organization_id,
            project_id=requirement.project_id,
            details={"requirement_id": requirement.requirement_id},
        )
        return requirement

    def register_plan_proposal(self, proposal: PlanProposal) -> PlanProposal:
        requirement = self.requirements.get(proposal.requirement_id)
        if requirement is None:
            raise KeyError(f"El requisito {proposal.requirement_id} no esta registrado")
        if (
            proposal.organization_id != requirement.organization_id
            or proposal.project_id != requirement.project_id
        ):
            raise ValueError("La propuesta no coincide con el namespace del requisito")
        for phase_id in proposal.phase_ids:
            phase = self.phases.get(phase_id)
            if phase is None:
                raise KeyError(f"La fase {phase_id} no esta registrada")
            if phase.requirement_id != proposal.requirement_id:
                raise ValueError("La fase de la propuesta no coincide con el requisito")
        for task_id in proposal.task_ids:
            task = self.tasks.get(task_id)
            if task is None:
                raise KeyError(f"La tarea {task_id} no esta registrada")
            if task.project_id != proposal.project_id:
                raise ValueError("La tarea de la propuesta no coincide con el proyecto")
        self.proposals[proposal.proposal_id] = proposal
        if self.state_store is not None:
            self.state_store.save_plan_proposal(proposal)
        updated_requirement = requirement.model_copy(
            update={"correlation_id": proposal.correlation_id}
        )
        self.requirements[requirement.requirement_id] = updated_requirement
        if self.state_store is not None:
            self.state_store.save_requirement(updated_requirement)
        for phase_id in proposal.phase_ids:
            phase = self.phases[phase_id]
            if phase.correlation_id != proposal.correlation_id:
                updated_phase = phase.model_copy(
                    update={"correlation_id": proposal.correlation_id}
                )
                self.phases[phase_id] = updated_phase
                if self.state_store is not None:
                    self.state_store.save_phase(updated_phase)
        for task_id in proposal.task_ids:
            task = self.tasks[task_id]
            if task.correlation_id != proposal.correlation_id:
                updated_task = task.model_copy(
                    update={"correlation_id": proposal.correlation_id}
                )
                self.tasks[task_id] = updated_task
                if self.state_store is not None:
                    self.state_store.save_task(updated_task)
        self._record_event(
            action="plan.proposed",
            status="accepted",
            organization_id=proposal.organization_id,
            project_id=proposal.project_id,
            requirement_id=proposal.requirement_id,
            correlation_id=proposal.correlation_id,
            details={"proposal_id": proposal.proposal_id, "model_profile": proposal.model_profile},
        )
        return proposal

    def approve_plan(self, proposal_id: str, *, approver: str) -> PlanProposal:
        proposal = self.proposals.get(proposal_id)
        if proposal is None:
            raise KeyError(f"La propuesta {proposal_id} no esta registrada")
        if proposal.status != "proposed":
            raise ValueError(f"La propuesta {proposal_id} no esta pendiente de aprobacion")
        if not approver.strip():
            raise ValueError("Se requiere un aprobador")
        for phase_id in proposal.phase_ids:
            self.approve_phase(phase_id, approver=approver)
        for task_id in proposal.task_ids:
            if self.tasks[task_id].state == "planned":
                self.approve_task(task_id, approver=approver)
        approved = proposal.model_copy(update={"status": "approved", "approved_by": approver})
        self.proposals[proposal_id] = approved
        if self.state_store is not None:
            self.state_store.save_plan_proposal(approved)
        self._record_event(
            action="plan.approve",
            status="accepted",
            organization_id=approved.organization_id,
            project_id=approved.project_id,
            requirement_id=approved.requirement_id,
            correlation_id=approved.correlation_id,
            details={"proposal_id": proposal_id, "approver": approver},
        )
        self._record_task_log(
            project_id=approved.project_id,
            organization_id=approved.organization_id,
            requirement_id=approved.requirement_id,
            actor="hermes",
            correlation_id=approved.correlation_id,
            message="plan.approve",
            metadata={"proposal_id": proposal_id, "approver": approver},
        )
        return approved

    def register_phase(self, phase: ProjectPhase) -> ProjectPhase:
        project = self.projects.get(phase.project_id)
        requirement = self.requirements.get(phase.requirement_id)
        if requirement is None:
            raise KeyError(f"El requisito {phase.requirement_id} no esta registrado")
        if (
            phase.organization_id != project.organization_id
            or requirement.project_id != phase.project_id
        ):
            raise ValueError("La fase no coincide con el namespace del proyecto")
        existing = self.phases.get(phase.phase_id)
        if existing and existing.model_dump(mode="json") != phase.model_dump(mode="json"):
            raise ValueError(f"La fase {phase.phase_id} ya esta registrada con otra configuracion")
        self.phases[phase.phase_id] = phase
        if self.state_store is not None:
            self.state_store.save_phase(phase)
        self._record_event(
            action="phase.register",
            status="accepted",
            organization_id=phase.organization_id,
            project_id=phase.project_id,
            details={"phase_id": phase.phase_id, "requirement_id": phase.requirement_id},
        )
        return phase

    def submit_task(self, task: TaskEnvelope) -> str:
        return self._dispatch_admitted_task(task, action="task.submit")

    def accept_admitted_task(self, task: TaskEnvelope) -> str:
        """Ingesta una tarea ya aceptada por el gateway Go.

        Este camino no vuelve a admitir la solicitud: valida el namespace
        local, persiste la transición y la entrega al coordinador Python de
        forma idempotente.
        """

        self._refresh_state_catalog()
        return self._dispatch_admitted_task(task, action="task.ingest")

    def _refresh_state_catalog(self) -> None:
        if self.state_store is None:
            return
        self.projects.projects.update(
            {project.project_id: project for project in self.state_store.load_projects()}
        )
        self.requirements.update(
            {item.requirement_id: item for item in self.state_store.load_requirements()}
        )
        self.proposals.update(
            {item.proposal_id: item for item in self.state_store.load_plan_proposals()}
        )
        self.phases.update({item.phase_id: item for item in self.state_store.load_phases()})
        self.tasks.update({task.task_id: task for task in self.state_store.load_tasks()})
        if isinstance(self.coordination, InMemoryCoordination):
            self.coordination.tasks.update(self.tasks)

    def _dispatch_admitted_task(self, task: TaskEnvelope, *, action: str) -> str:
        project = self.projects.get(task.project_id)
        if task.organization_id != project.organization_id:
            raise ValueError("La organizacion de la tarea no coincide con el proyecto")
        if task.repository != project.repository:
            raise ValueError("El repositorio de la tarea no coincide con el proyecto")
        if task.requirement_id is not None:
            requirement = self.requirements.get(task.requirement_id)
            if requirement is None:
                raise KeyError(f"El requisito {task.requirement_id} no esta registrado")
            if requirement.project_id != task.project_id:
                raise ValueError("El requisito de la tarea no coincide con el proyecto")
        if task.phase_id is not None:
            phase = self.phases.get(task.phase_id)
            if phase is None:
                raise KeyError(f"La fase {task.phase_id} no esta registrada")
            if phase.project_id != task.project_id or phase.requirement_id != task.requirement_id:
                raise ValueError("La fase de la tarea no coincide con su requisito")
            if task.correlation_id is None and phase.correlation_id is not None:
                task = task.model_copy(update={"correlation_id": phase.correlation_id})
        if task.source == "requirement" and (task.requirement_id is None or task.phase_id is None):
            raise ValueError("Una tarea derivada requiere requirement_id y phase_id")
        with self._task_lock:
            existing = self.tasks.get(task.task_id)
            if existing:
                existing_data = existing.model_dump(mode="json")
                incoming_data = task.model_dump(mode="json")
                for data in (existing_data, incoming_data):
                    data.pop("state", None)
                    data.pop("created_at", None)
                if existing_data != incoming_data:
                    raise ValueError(f"La tarea {task.task_id} ya existe con otra configuracion")
                return task.task_id
        if task.state == "planned":
            self._persist_task_acceptance(task, action="task.plan")
            return task.task_id
        return self.dispatcher.submit(
            task,
            persist=lambda: self._persist_task_acceptance(task, action=action),
        )

    def record_result(self, result: AgentResult) -> None:
        self._refresh_state_catalog()
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
            requirement_id=task.requirement_id,
            phase_id=task.phase_id,
            task_id=task.task_id,
            correlation_id=task.correlation_id or f"task:{task.task_id}",
            details={"task_id": result.task_id, "result_status": result.status},
        )
        self._record_task_log(
            task=task,
            level="info" if result.status == "succeeded" else "error",
            message="task.result",
            metadata={"result_status": result.status, "summary": result.summary},
        )
        self._refresh_planning_state()

    def _record_task_log(
        self,
        *,
        task: TaskEnvelope | None = None,
        level: str = "info",
        message: str,
        metadata: dict[str, object] | None = None,
        requirement_id: str | None = None,
        phase_id: str | None = None,
        task_id: str | None = None,
        organization_id: str | None = None,
        project_id: str | None = None,
        actor: str = "trama",
        correlation_id: str | None = None,
    ) -> TaskLog:
        if task is not None:
            organization_id = task.organization_id
            project_id = task.project_id
            requirement_id = task.requirement_id
            phase_id = task.phase_id
            task_id = task.task_id
            correlation_id = task.correlation_id or f"task:{task.task_id}"
        if project_id is None:
            raise ValueError("Un log requiere project_id")
        safe_message, safe_metadata = sanitize_message(message, metadata or {})
        if self.state_store is not None and task_id is not None:
            sequence = self.state_store.count_task_logs(
                organization_id=organization_id,
                project_id=project_id,
                task_id=task_id,
            ) + 1
        else:
            sequence = sum(
                log.project_id == project_id and log.task_id == task_id
                for log in self._logs
            ) + 1
        log = TaskLog(
            organization_id=organization_id or "default",
            project_id=project_id,
            requirement_id=requirement_id,
            phase_id=phase_id,
            task_id=task_id,
            actor=actor,
            correlation_id=correlation_id or f"project:{project_id}",
            level=level,
            message=safe_message,
            metadata=safe_metadata,
            sequence=sequence,
        )
        if self.state_store is not None:
            self.state_store.append_task_log(log)
        else:
            self._logs.append(log)
        return log

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
        self, organization_id: str, project_id: str, query: str, agent_id: str | None = None
    ) -> list[MemoryCandidate]:
        project = self.projects.get(project_id)
        if organization_id != project.organization_id:
            raise ValueError("La organizacion de la busqueda no coincide con el proyecto")
        return list(self.context_memory.search(organization_id, project_id, query, agent_id))

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
        self._refresh_state_catalog()
        return list(self.projects.projects.values())

    def list_requirements(self, project_id: str | None = None) -> list[Requirement]:
        self._refresh_state_catalog()
        items = list(self.requirements.values())
        return [item for item in items if project_id is None or item.project_id == project_id]

    def get_requirement(self, requirement_id: str) -> Requirement:
        self._refresh_state_catalog()
        try:
            return self.requirements[requirement_id]
        except KeyError as exc:
            raise KeyError(f"El requisito {requirement_id} no esta registrado") from exc

    def list_phases(self, project_id: str | None = None) -> list[ProjectPhase]:
        self._refresh_state_catalog()
        items = sorted(
            self.phases.values(),
            key=lambda item: (item.project_id, item.sequence, item.phase_id),
        )
        return [item for item in items if project_id is None or item.project_id == project_id]

    def approve_phase(self, phase_id: str, *, approver: str) -> ProjectPhase:
        self._refresh_state_catalog()
        phase = self.phases.get(phase_id)
        if phase is None:
            raise KeyError(f"La fase {phase_id} no esta registrada")
        if not approver.strip():
            raise ValueError("Se requiere un aprobador")
        updated = phase.model_copy(update={"approved_by": approver, "status": "ready"})
        if not self._phase_dependencies_complete(updated):
            updated = updated.model_copy(update={"status": "planned"})
        self.phases[phase_id] = updated
        if self.state_store is not None:
            self.state_store.save_phase(updated)
        self._record_event(
            action="phase.approve",
            status="accepted",
            organization_id=updated.organization_id,
            project_id=updated.project_id,
            details={"phase_id": phase_id, "approver": approver},
        )
        self._refresh_planning_state()
        return self.phases[phase_id]

    def approve_task(self, task_id: str, *, approver: str) -> TaskEnvelope:
        self._refresh_state_catalog()
        task = self.get_task(task_id)
        if task.state != "planned":
            raise ValueError(f"La tarea {task_id} no esta pendiente de aprobacion")
        if not approver.strip():
            raise ValueError("Se requiere un aprobador")
        updated = task.model_copy(update={"approved_by": approver})
        if self._task_ready_for_dispatch(updated):
            updated = updated.model_copy(update={"state": "accepted"})
            self.dispatcher.submit(
                updated,
                persist=lambda: self._persist_task_acceptance(updated, action="task.approve"),
            )
        else:
            self._persist_task_acceptance(updated, action="task.approve")
        return updated

    def get_project(self, project_id: str) -> ProjectManifest:
        self._refresh_state_catalog()
        return self.projects.get(project_id)

    def list_tasks(self) -> list[TaskEnvelope]:
        self._refresh_state_catalog()
        return list(self.tasks.values())

    def get_task(self, task_id: str) -> TaskEnvelope:
        self._refresh_state_catalog()
        try:
            return self.tasks[task_id]
        except KeyError as exc:
            raise KeyError(f"La tarea {task_id} no esta registrada") from exc

    def record_task_log(self, log: TaskLog) -> TaskLog:
        project = self.projects.get(log.project_id)
        if log.organization_id != project.organization_id:
            raise ValueError("La organizacion del log no coincide con el proyecto")
        if log.task_id is not None:
            task = self.get_task(log.task_id)
            if task.project_id != log.project_id:
                raise ValueError("La tarea del log no coincide con el proyecto")
        if log.phase_id is not None:
            phase = self.phases.get(log.phase_id)
            if phase is None:
                raise KeyError(f"La fase {log.phase_id} no esta registrada")
            if phase.project_id != log.project_id:
                raise ValueError("La fase del log no coincide con el proyecto")
        message, metadata = sanitize_message(log.message, log.metadata)
        safe_log = log.model_copy(update={"message": message, "metadata": metadata})
        if self.state_store is not None:
            self.state_store.append_task_log(safe_log)
        else:
            self._logs.append(safe_log)
        return safe_log

    def _event_items(self) -> list[OperationEvent]:
        if self.state_store is not None:
            return list(self.state_store.list_events(1000))
        return list(self._events)

    def _log_items(
        self,
        *,
        task_id: str | None = None,
        phase_id: str | None = None,
        requirement_id: str | None = None,
        project_id: str | None = None,
    ) -> list[TaskLog]:
        if self.state_store is not None:
            return list(
                self.state_store.list_task_logs(
                    task_id=task_id,
                    phase_id=phase_id,
                    requirement_id=requirement_id,
                    project_id=project_id,
                    limit=1000,
                )
            )
        return [
            log
            for log in self._logs
            if (task_id is None or log.task_id == task_id)
            and (phase_id is None or log.phase_id == phase_id)
            and (requirement_id is None or log.requirement_id == requirement_id)
            and (project_id is None or log.project_id == project_id)
        ]

    @staticmethod
    def _timeline_entries(
        events: list[OperationEvent], logs: list[TaskLog]
    ) -> list[TimelineEntry]:
        items: list[tuple[object, str, OperationEvent | TaskLog]] = [
            (event.created_at, "event", event) for event in events
        ] + [(log.created_at, "log", log) for log in logs]
        items.sort(key=lambda item: (item[0], item[1]))
        entries: list[TimelineEntry] = []
        for sequence, (_, kind, item) in enumerate(items, start=1):
            if kind == "event":
                event = item
                entries.append(
                    TimelineEntry(
                        entry_id=event.event_id,
                        kind="event",
                        created_at=event.created_at,
                        sequence=sequence,
                        actor=event.actor,
                        action=event.action,
                        status=event.status,
                        metadata=event.details,
                        correlation_id=event.correlation_id,
                        requirement_id=event.requirement_id,
                        phase_id=event.phase_id,
                        task_id=event.task_id,
                    )
                )
            else:
                log = item
                entries.append(
                    TimelineEntry(
                        entry_id=log.log_id,
                        kind="log",
                        created_at=log.created_at,
                        sequence=sequence,
                        actor=log.actor,
                        level=log.level,
                        message=log.message,
                        metadata=log.metadata,
                        correlation_id=log.correlation_id,
                        requirement_id=log.requirement_id,
                        phase_id=log.phase_id,
                        task_id=log.task_id,
                    )
                )
        return entries

    def task_timeline(self, task_id: str, limit: int = 100) -> list[TimelineEntry]:
        task = self.get_task(task_id)
        events = [
            event
            for event in self._event_items()
            if event.task_id == task_id or event.details.get("task_id") == task_id
        ]
        entries = self._timeline_entries(
            events,
            self._log_items(task_id=task_id, project_id=task.project_id),
        )
        return entries[-max(1, min(limit, 1000)) :]

    def phase_timeline(self, phase_id: str, limit: int = 100) -> list[TimelineEntry]:
        phase = self.phases.get(phase_id)
        if phase is None:
            raise KeyError(f"La fase {phase_id} no esta registrada")
        task_ids = {task.task_id for task in self.tasks.values() if task.phase_id == phase_id}
        events = [
            event
            for event in self._event_items()
            if event.phase_id == phase_id
            or event.details.get("phase_id") == phase_id
            or event.task_id in task_ids
            or event.details.get("task_id") in task_ids
        ]
        logs = self._log_items(phase_id=phase_id, project_id=phase.project_id)
        entries = self._timeline_entries(events, logs)
        return entries[-max(1, min(limit, 1000)) :]

    def list_logs(
        self,
        *,
        organization_id: str | None = None,
        project_id: str | None = None,
        task_id: str | None = None,
        phase_id: str | None = None,
        requirement_id: str | None = None,
        level: str | None = None,
        limit: int = 100,
    ) -> list[TaskLog]:
        if self.state_store is not None:
            return list(
                self.state_store.list_task_logs(
                    organization_id=organization_id,
                    project_id=project_id,
                    task_id=task_id,
                    phase_id=phase_id,
                    requirement_id=requirement_id,
                    level=level,
                    limit=limit,
                )
            )
        items = self._log_items(
            task_id=task_id,
            phase_id=phase_id,
            requirement_id=requirement_id,
            project_id=project_id,
        )
        if organization_id is not None:
            items = [item for item in items if item.organization_id == organization_id]
        if level is not None:
            items = [item for item in items if item.level == level]
        return items[-max(1, min(limit, 1000)) :]

    def get_plan_proposal(self, proposal_id: str) -> PlanProposal:
        self._refresh_state_catalog()
        try:
            return self.proposals[proposal_id]
        except KeyError as exc:
            raise KeyError(f"La propuesta {proposal_id} no esta registrada") from exc

    def _parallel_groups(self, phases: list[ProjectPhase]) -> list[dict[str, list[str]]]:
        groups: dict[tuple[str, ...], list[ProjectPhase]] = {}
        for phase in phases:
            if phase.status not in {"ready", "in_progress"}:
                continue
            if not self._phase_dependencies_complete(phase):
                continue
            groups.setdefault(tuple(sorted(phase.depends_on)), []).append(phase)
        return [
            {
                "phase_ids": [
                    phase.phase_id for phase in sorted(items, key=lambda item: item.sequence)
                ]
            }
            for items in groups.values()
        ]

    def overview(self, project_id: str | None = None) -> dict[str, object]:
        tasks = [
            task
            for task in self.tasks.values()
            if project_id is None or task.project_id == project_id
        ]
        phases = self.list_phases(project_id)
        phase_views: list[dict[str, object]] = []
        for phase in phases:
            phase_tasks = [task for task in tasks if task.phase_id == phase.phase_id]
            completed = sum(task.state == "succeeded" for task in phase_tasks)
            blocked = any(task.state in {"blocked", "failed"} for task in phase_tasks)
            phase_views.append(
                {
                    **phase.model_dump(mode="json"),
                    "total_tasks": len(phase_tasks),
                    "completed_tasks": completed,
                    "progress": (completed / len(phase_tasks) if phase_tasks else 0.0),
                    "status": (
                        "blocked"
                        if blocked
                        else (
                            "completed"
                            if phase_tasks and completed == len(phase_tasks)
                            else phase.status
                        )
                    ),
                }
            )
        queue = [
            {
                **task.model_dump(mode="json"),
                "queue_state": {
                    "planned": "awaiting_approval",
                    "accepted": "queued",
                    "running": "running",
                    "blocked": "blocked",
                }.get(task.state, task.state),
            }
            for task in tasks
            if task.state in {"planned", "accepted", "running", "blocked"}
        ]
        agents = []
        for agent in self.list_agents():
            agent_tasks = [task for task in tasks if task.actor == agent["agent_id"]]
            agents.append(
                {
                    **agent,
                    "active": sum(task.state in {"accepted", "running"} for task in agent_tasks),
                    "completed": sum(task.state == "succeeded" for task in agent_tasks),
                    "blocked": sum(task.state in {"blocked", "failed"} for task in agent_tasks),
                }
            )
        pending_approval = [
            phase.phase_id
            for phase in phases
            if phase.status == "planned" and not phase.approved_by
        ]
        pending_approval.extend(
            task.task_id for task in tasks if task.state == "planned" and not task.approved_by
        )
        blocked_dependencies = [
            phase.phase_id
            for phase in phases
            if phase.approved_by and not self._phase_dependencies_complete(phase)
        ]
        blocked_dependencies.extend(
            task.task_id
            for task in tasks
            if task.state == "planned"
            and task.approved_by
            and not self._task_ready_for_dispatch(task)
        )
        activity = self._timeline_entries(
            self._event_items(), self._log_items(project_id=project_id)
        )
        return {
            "project_id": project_id,
            "requirements": [
                item.model_dump(mode="json")
                for item in self.list_requirements(project_id)
            ],
            "phases": phase_views,
            "queue": queue,
            "agents": agents,
            "queue_status": self.dispatcher.status(),
            "parallel_groups": self._parallel_groups(phases),
            "pending_approval": pending_approval,
            "blocked_dependencies": blocked_dependencies,
            "latest_activity": [item.model_dump(mode="json") for item in activity[-12:]],
        }

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
        self.dispatcher.submit(
            updated,
            persist=lambda: self._transition_task(
                updated,
                "task.retry",
                "accepted",
                {"task_id": task_id},
            ),
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
            **self.dispatcher.status(),
        }

    def wait_for_idle(self, timeout: float) -> bool:
        return self.dispatcher.wait_for_idle(timeout)

    def close(self) -> None:
        self.dispatcher.close()
