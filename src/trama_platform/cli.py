"""CLI de desarrollo y validacion de TRAMA."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from .api import create_app
from .contracts import (
    AgentResult,
    MemoryCandidate,
    MemorySearchRequest,
    ModelRequest,
    ProjectManifest,
    PromotionRequest,
    TaskEnvelope,
    ToolInvocation,
)
from .mcp_server import run_mcp
from .project import load_project_manifest
from .settings import TramaSettings

CONTRACTS = {
    "project-manifest": ProjectManifest,
    "task-envelope": TaskEnvelope,
    "agent-result": AgentResult,
    "memory-candidate": MemoryCandidate,
    "memory-search-request": MemorySearchRequest,
    "promotion-request": PromotionRequest,
    "tool-invocation": ToolInvocation,
    "model-request": ModelRequest,
}


def _export_schemas(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name, model in CONTRACTS.items():
        output = destination / f"{name}.v1.schema.json"
        output.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(output)


def main() -> None:
    parser = argparse.ArgumentParser(prog="trama")
    subparsers = parser.add_subparsers(dest="command", required=True)
    settings = TramaSettings.from_env()

    api_parser = subparsers.add_parser("api")
    api_parser.add_argument("--host", default=settings.api_host)
    api_parser.add_argument("--port", type=int, default=settings.api_port)

    mcp_parser = subparsers.add_parser("mcp")
    mcp_parser.add_argument("--api-url", default=settings.api_url)

    project_parser = subparsers.add_parser("validate-project")
    project_parser.add_argument("path")

    schema_parser = subparsers.add_parser("export-schemas")
    schema_parser.add_argument("destination", type=Path)

    args = parser.parse_args()
    if args.command == "api":
        import uvicorn

        uvicorn.run(create_app(), host=args.host, port=args.port)
    elif args.command == "mcp":
        run_mcp(args.api_url)
    elif args.command == "validate-project":
        print(
            json.dumps(
                load_project_manifest(args.path).model_dump(mode="json"),
                ensure_ascii=False,
                indent=2,
            )
        )
    elif args.command == "export-schemas":
        _export_schemas(args.destination)
