"""Carga segura del manifiesto de un proyecto conectado."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from .contracts import ProjectManifest


def load_project_manifest(path: str | Path) -> ProjectManifest:
    manifest_path = Path(path).resolve()
    if manifest_path.suffix.lower() not in {".yaml", ".yml"}:
        raise ValueError("El manifiesto debe tener extension .yaml o .yml")
    raw: Any = yaml.safe_load(manifest_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError("El manifiesto debe contener un objeto YAML")
    return ProjectManifest.model_validate(raw)
