"""Identidad y namespace del request que atraviesan el control plane."""

from __future__ import annotations

from dataclasses import dataclass
from secrets import token_hex
from typing import Mapping


class ContextError(ValueError):
    """El request no contiene el contexto mínimo de autorización."""


@dataclass(frozen=True)
class RequestContext:
    identity: str
    organization_id: str
    project_id: str | None
    scopes: frozenset[str]
    correlation_id: str

    @classmethod
    def from_headers(
        cls,
        headers: Mapping[str, str],
        *,
        default_organization: str = "default",
        required: bool = False,
    ) -> "RequestContext":
        organization_id = headers.get("x-organization-id", "").strip()
        if not organization_id:
            if required:
                raise ContextError("X-Organization-ID es obligatorio")
            organization_id = default_organization
        project_id = headers.get("x-project-id", "").strip() or None
        identity = headers.get("x-actor-id", "").strip() or "anonymous"
        raw_scopes = headers.get("x-scopes", "")
        scopes = frozenset(scope for scope in raw_scopes.split() if scope)
        correlation_id = headers.get("x-correlation-id", "").strip() or token_hex(16)
        return cls(
            identity=identity,
            organization_id=organization_id,
            project_id=project_id,
            scopes=scopes,
            correlation_id=correlation_id,
        )

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes or "*" in self.scopes
