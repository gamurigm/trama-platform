"""Native adapter for Semantica's AgentContext API."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from .contracts import MemoryCandidate
from .namespaces import can_read_candidate
from .ports import ContextMemoryPort


class SemanticaContextAdapter(ContextMemoryPort):
    """Store and retrieve TRAMA candidates through a Semantica AgentContext.

    Semantica explicitly recommends native ``AgentContext`` usage for Python
    services. The adapter keeps TRAMA's typed candidate index while sending
    the same provenance into Semantica metadata for semantic retrieval.
    """

    def __init__(self, context: Any, *, max_results: int = 20) -> None:
        self.context = context
        self.max_results = max(1, min(max_results, 100))
        self.candidates: dict[str, MemoryCandidate] = {}

    def put_candidate(self, candidate: MemoryCandidate) -> str:
        metadata = candidate.model_dump(mode="json")
        content = f"{candidate.subject}: {candidate.fact}"
        self.context.store(
            content,
            metadata=metadata,
            memory_id=candidate.candidate_id,
            extract_entities=False,
            extract_relationships=False,
        )
        self.candidates[candidate.candidate_id] = candidate
        return candidate.candidate_id

    def get_candidate(self, candidate_id: str) -> MemoryCandidate | None:
        return self.candidates.get(candidate_id)

    def search(
        self, organization_id: str, project_id: str, query: str, agent_id: str | None = None
    ) -> Sequence[MemoryCandidate]:
        raw = self.context.retrieve(query, max_results=self.max_results)
        if isinstance(raw, dict):
            raw = raw.get("results", [])
        candidates: list[MemoryCandidate] = []
        for item in raw or []:
            if isinstance(item, MemoryCandidate):
                candidate = item
            else:
                metadata = dict(item.get("metadata") or {})
                content = str(item.get("content", item.get("text", "")))
                memory_id = item.get("id", item.get("memory_id", "semantica-memory"))
                metadata.setdefault("candidate_id", str(memory_id))
                metadata.setdefault("project_id", project_id)
                metadata.setdefault("organization_id", organization_id)
                metadata.setdefault("subject", "Semantica memory")
                metadata.setdefault("fact", content)
                metadata.setdefault("source", "semantica")
                metadata.setdefault(
                    "evidence",
                    [{"source": "semantica", "locator": metadata["candidate_id"]}],
                )
                metadata.setdefault("confidence", 1.0)
                candidate = MemoryCandidate.model_validate(metadata)
            self.candidates[candidate.candidate_id] = candidate
            if can_read_candidate(candidate, organization_id, project_id, agent_id):
                candidates.append(candidate)
        return candidates
