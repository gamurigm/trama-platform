"""Reglas de namespace para evitar mezcla accidental entre proyectos."""

from __future__ import annotations

from collections.abc import Iterable, Iterator, Mapping
from typing import Generic, TypeVar

from .contracts import MemoryCandidate, PromotionRequest

NamespaceKey = tuple[str, str]
ValueT = TypeVar("ValueT")


def namespace_key(organization_id: str, entity_id: str) -> NamespaceKey:
    return organization_id, entity_id


class ScopedStore(Generic[ValueT]):
    """Coleccion en memoria indexada por organizacion e identificador."""

    def __init__(self) -> None:
        self._items: dict[NamespaceKey, ValueT] = {}

    def __getitem__(self, key: NamespaceKey | str) -> ValueT:
        if isinstance(key, tuple):
            return self._items[key]
        return self.find(key)

    def __setitem__(self, key: NamespaceKey | str, value: ValueT) -> None:
        if isinstance(key, tuple):
            scoped_key = key
        else:
            scoped_key = namespace_key(str(getattr(value, "organization_id", "default")), key)
        self._items[scoped_key] = value

    def __contains__(self, key: object) -> bool:
        if isinstance(key, tuple):
            return key in self._items
        if not isinstance(key, str):
            return False
        try:
            self.find(key)
        except (KeyError, ValueError):
            return False
        return True

    def __iter__(self) -> Iterator[NamespaceKey]:
        return iter(self._items)

    def __len__(self) -> int:
        return len(self._items)

    def get(
        self, key: NamespaceKey | str, default: ValueT | None = None
    ) -> ValueT | None:
        try:
            return self[key]
        except (KeyError, ValueError):
            return default

    def find(self, entity_id: str, *, organization_id: str | None = None) -> ValueT:
        if organization_id is not None:
            try:
                return self._items[namespace_key(organization_id, entity_id)]
            except KeyError as exc:
                raise KeyError(f"{entity_id} no esta registrado en la organizacion") from exc
        matches = [value for key, value in self._items.items() if key[1] == entity_id]
        if not matches:
            raise KeyError(f"{entity_id} no esta registrado")
        if len(matches) > 1:
            raise ValueError(
                f"La busqueda del identificador {entity_id} es ambigua; indique la organizacion"
            )
        return matches[0]

    def update(
        self,
        values: Mapping[NamespaceKey | str, ValueT]
        | Iterable[tuple[NamespaceKey | str, ValueT]],
    ) -> None:
        if isinstance(values, ScopedStore):
            items = values.items()
        elif isinstance(values, Mapping):
            items = values.items()
        else:
            items = values
        for key, value in items:
            self[key] = value

    def values(self):
        return self._items.values()

    def items(self):
        return self._items.items()


def context_namespace(organization_id: str, project_id: str, agent_id: str) -> str:
    return f"context/{organization_id}/{project_id}/{agent_id}"


def knowledge_namespace(organization_id: str, project_id: str) -> str:
    return f"knowledge/{organization_id}/{project_id}"


def artifact_namespace(organization_id: str, project_id: str, task_id: str) -> str:
    return f"artifacts/{organization_id}/{project_id}/{task_id}"


def can_read_candidate(
    candidate: MemoryCandidate,
    organization_id: str,
    project_id: str,
    agent_id: str | None = None,
) -> bool:
    if candidate.organization_id != organization_id:
        return False
    if candidate.visibility == "shared":
        return True
    if candidate.project_id != project_id:
        return False
    if candidate.visibility == "project":
        return True
    return candidate.visibility == "private" and candidate.agent_id == agent_id


def can_promote(request: PromotionRequest, candidate: MemoryCandidate) -> bool:
    return (
        request.organization_id == candidate.organization_id
        and request.project_id == candidate.project_id
        and request.status == "approved"
    )
