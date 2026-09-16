"""CLI gateway de TRAMA."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

import httpx

from .adapters import CcccCliAdapter
from .api import create_app
from .contracts import (
    AgentResult,
    MemoryCandidate,
    MemorySearchRequest,
    ModelRequest,
    OperationEvent,
    ProjectManifest,
    ProjectPhase,
    PromotionRequest,
    Requirement,
    TaskEnvelope,
    ToolInvocation,
)
from .hermes import HermesAdapter
from .lifecycle import GatewaySupervisor
from .mcp_server import TramaApiClient, TramaApiError, run_mcp
from .ports import CoordinationPort
from .project import load_project_manifest
from .semantica_adapter import SemanticaContextAdapter
from .settings import TramaSettings
from .state_store import SqliteStateStore
from .utopia_mcp import UtopiaMcpAdapter
from .worker import run_task_worker

CONTRACTS = {
    "project-manifest": ProjectManifest,
    "requirement": Requirement,
    "project-phase": ProjectPhase,
    "task-envelope": TaskEnvelope,
    "agent-result": AgentResult,
    "memory-candidate": MemoryCandidate,
    "memory-search-request": MemorySearchRequest,
    "promotion-request": PromotionRequest,
    "tool-invocation": ToolInvocation,
    "model-request": ModelRequest,
    "operation-event": OperationEvent,
}

# Valores internos mínimos requeridos por AgentContext; no son opciones de
# despliegue y por eso no se exponen como variables de entorno.
SEMANTICA_VECTOR_BACKEND = "inmemory"
SEMANTICA_VECTOR_DIMENSION = 768


def _export_schemas(destination: Path) -> None:
    destination.mkdir(parents=True, exist_ok=True)
    for name, model in CONTRACTS.items():
        output = destination / f"{name}.v1.schema.json"
        output.write_text(
            json.dumps(model.model_json_schema(), ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        print(output)


def _emit(value: Any, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
        return
    if isinstance(value, dict):
        for key, item in value.items():
            print(f"{key}: {item}")
    elif isinstance(value, list):
        print(json.dumps(value, ensure_ascii=False, indent=2, default=str))
    else:
        print(value)


def build_coordination(settings: TramaSettings) -> CoordinationPort | None:
    """Construye el coordinador externo solicitado por configuración."""

    backend = settings.coordination_backend.casefold()
    if backend == "memory":
        return None
    if backend == "cccc":
        return CcccCliAdapter(
            executable=settings.cccc_executable,
            timeout_seconds=settings.cccc_timeout_seconds,
        )
    raise ValueError(
        "TRAMA_COORDINATION_BACKEND debe ser 'memory' o 'cccc'"
    )


def build_context_memory(settings: TramaSettings):
    if settings.semantica_kg_path is None:
        return None
    try:
        from semantica.context import AgentContext, ContextGraph
        from semantica.vector_store import VectorStore
    except ImportError as exc:
        raise RuntimeError(
            "Semantica nativa requiere instalar el paquete semantica; "
            "instala la dependencia opcional 'integrations'"
        ) from exc
    context = AgentContext(
        vector_store=VectorStore(
            backend=SEMANTICA_VECTOR_BACKEND,
            dimension=SEMANTICA_VECTOR_DIMENSION,
        ),
        knowledge_graph=ContextGraph(advanced_analytics=True),
        decision_tracking=True,
    )
    context.load(settings.semantica_kg_path)
    return SemanticaContextAdapter(context)


def build_canonical_knowledge(settings: TramaSettings):
    if settings.utopia_url is None and settings.utopia_kb_id is None:
        return None
    if not settings.utopia_url or not settings.utopia_kb_id or not settings.utopia_token:
        raise ValueError(
            "Utopia requiere TRAMA_UTOPIA_URL, TRAMA_UTOPIA_KB_ID y TRAMA_UTOPIA_TOKEN"
        )
    return UtopiaMcpAdapter(
        settings.utopia_url,
        settings.utopia_kb_id,
        token=settings.utopia_token,
    )


def _add_api_options(parser: argparse.ArgumentParser, settings: TramaSettings) -> None:
    parser.add_argument("--api-url", default=settings.api_url)
    parser.add_argument("--json", action="store_true", dest="as_json")


def _add_control_commands(subparsers: argparse._SubParsersAction, settings: TramaSettings) -> None:
    up_parser = subparsers.add_parser("up", help="Inicia el control plane local")
    up_parser.add_argument("--json", action="store_true", dest="as_json")
    down_parser = subparsers.add_parser("down", help="Detiene el control plane iniciado por TRAMA")
    down_parser.add_argument("--json", action="store_true", dest="as_json")

    status_parser = subparsers.add_parser("status", help="Muestra el estado del control plane")
    _add_api_options(status_parser, settings)

    doctor_parser = subparsers.add_parser("doctor", help="Comprueba la salud de TRAMA")
    _add_api_options(doctor_parser, settings)

    project_parser = subparsers.add_parser("project", help="Opera proyectos registrados")
    project_commands = project_parser.add_subparsers(dest="project_command", required=True)
    project_list = project_commands.add_parser("list")
    _add_api_options(project_list, settings)
    project_inspect = project_commands.add_parser("inspect")
    project_inspect.add_argument("project_id")
    _add_api_options(project_inspect, settings)
    project_register = project_commands.add_parser("register")
    project_register.add_argument("manifest")
    _add_api_options(project_register, settings)

    task_parser = subparsers.add_parser("task", help="Opera tareas del control plane")
    task_commands = task_parser.add_subparsers(dest="task_command", required=True)
    task_list = task_commands.add_parser("list")
    _add_api_options(task_list, settings)
    task_inspect = task_commands.add_parser("inspect")
    task_inspect.add_argument("task_id")
    _add_api_options(task_inspect, settings)
    task_result = task_commands.add_parser("result")
    task_result.add_argument("task_id")
    _add_api_options(task_result, settings)
    for command_name in ("cancel", "retry"):
        task_transition = task_commands.add_parser(command_name)
        task_transition.add_argument("task_id")
        task_transition.add_argument("--confirm", action="store_true")
        _add_api_options(task_transition, settings)
    task_submit = task_commands.add_parser("submit")
    task_submit.add_argument("--file", required=True)
    _add_api_options(task_submit, settings)

    audit_parser = subparsers.add_parser("audit", help="Consulta eventos de auditoria")
    audit_commands = audit_parser.add_subparsers(dest="audit_command", required=True)
    audit_list = audit_commands.add_parser("list")
    audit_list.add_argument("--limit", type=int, default=100)
    _add_api_options(audit_list, settings)

    context_parser = subparsers.add_parser("context", help="Consulta memoria contextual")
    context_commands = context_parser.add_subparsers(dest="context_command", required=True)
    context_search = context_commands.add_parser("search")
    context_search.add_argument("--organization", default=settings.organization_id)
    context_search.add_argument("--project", required=True)
    context_search.add_argument("--agent")
    context_search.add_argument("query")
    _add_api_options(context_search, settings)

    agent_parser = subparsers.add_parser("agent", help="Consulta agentes y actores")
    agent_commands = agent_parser.add_subparsers(dest="agent_command", required=True)
    agent_list = agent_commands.add_parser("list")
    _add_api_options(agent_list, settings)

    knowledge_parser = subparsers.add_parser("knowledge", help="Opera candidatos de conocimiento")
    knowledge_commands = knowledge_parser.add_subparsers(
        dest="knowledge_command", required=True
    )
    for command_name in ("candidates", "review"):
        candidate_command = knowledge_commands.add_parser(command_name)
        candidate_command.add_argument("--organization", default=settings.organization_id)
        candidate_command.add_argument("--project", required=True)
        _add_api_options(candidate_command, settings)
    for command_name in ("validate", "reject"):
        review_command = knowledge_commands.add_parser(command_name)
        review_command.add_argument("candidate_id")
        review_command.add_argument("--reviewer", required=True)
        review_command.add_argument("--organization", default=settings.organization_id)
        review_command.add_argument("--project", required=True)
        _add_api_options(review_command, settings)
    promote_command = knowledge_commands.add_parser("promote")
    promote_command.add_argument("--file", required=True)
    promote_command.add_argument("--confirm", action="store_true")
    _add_api_options(promote_command, settings)

    model_parser = subparsers.add_parser("model", help="Consulta el gateway de modelos")
    model_commands = model_parser.add_subparsers(dest="model_command", required=True)
    model_list = model_commands.add_parser("list")
    model_list.add_argument("--json", action="store_true", dest="as_json")

    config_parser = subparsers.add_parser("config", help="Consulta configuración no sensible")
    config_commands = config_parser.add_subparsers(dest="config_command", required=True)
    config_get = config_commands.add_parser("get")
    config_get.add_argument("--key")
    config_get.add_argument("--json", action="store_true", dest="as_json")

    subparsers.add_parser(
        "worker", help="Consume tareas admitidas por el gateway Go mediante NATS"
    )

    hermes_parser = subparsers.add_parser("hermes", help="Opera la integracion local de Hermes")
    hermes_commands = hermes_parser.add_subparsers(dest="hermes_command", required=True)
    hermes_check = hermes_commands.add_parser("check")
    hermes_check.add_argument("--json", action="store_true", dest="as_json")
    hermes_configure = hermes_commands.add_parser("configure")
    hermes_configure.add_argument("--path", default=settings.hermes_config_path)
    hermes_configure.add_argument("--api-url", default=settings.api_url)
    hermes_configure.add_argument("--json", action="store_true", dest="as_json")
    hermes_run = hermes_commands.add_parser("run")
    hermes_run.add_argument("--cwd", default=None)
    hermes_run.add_argument("hermes_args", nargs=argparse.REMAINDER)


def _run_control_command(args: argparse.Namespace) -> None:
    if args.command == "worker":
        run_task_worker(TramaSettings.from_env())
        return

    if args.command in {"up", "down"}:
        settings = TramaSettings.from_env()
        command = [
            sys.executable,
            "-m",
            "trama_platform",
            "api",
            "--host",
            settings.api_host,
            "--port",
            str(settings.api_port),
        ]
        supervisor = GatewaySupervisor(state_dir=settings.state_dir, command=command)
        result = supervisor.start() if args.command == "up" else supervisor.stop()
        _emit(result, as_json=args.as_json)
        return

    if args.command == "status":
        _emit(TramaApiClient(args.api_url).get_status(), as_json=args.as_json)
        return

    if args.command == "doctor":
        try:
            status = TramaApiClient(args.api_url).get_status()
        except (TramaApiError, httpx.HTTPError) as exc:
            _emit(
                {"status": "error", "code": "api_unavailable", "message": str(exc)},
                as_json=args.as_json,
            )
            raise SystemExit(1) from exc
        _emit({"status": "ok", "api": status}, as_json=args.as_json)
        return

    if args.command == "project":
        client = TramaApiClient(args.api_url)
        if args.project_command == "list":
            _emit(client.list_projects(), as_json=args.as_json)
        elif args.project_command == "inspect":
            _emit(client.get_project(args.project_id), as_json=args.as_json)
        else:
            manifest = load_project_manifest(args.manifest)
            _emit(client.register_project(manifest), as_json=args.as_json)
        return

    if args.command == "task":
        client = TramaApiClient(args.api_url)
        if args.task_command == "list":
            value = client.list_tasks()
        elif args.task_command == "inspect":
            value = client.get_task(args.task_id)
        elif args.task_command == "result":
            value = client.get_task_result(args.task_id)
        elif args.task_command in {"cancel", "retry"}:
            if not args.confirm:
                raise SystemExit("confirm required for task transition")
            transition = client.cancel_task if args.task_command == "cancel" else client.retry_task
            value = transition(args.task_id)
        else:
            value = client.submit_task(
                TaskEnvelope.model_validate(json.loads(Path(args.file).read_text(encoding="utf-8")))
            )
        _emit(value, as_json=args.as_json)
        return

    if args.command == "audit" and args.audit_command == "list":
        _emit(
            TramaApiClient(args.api_url).list_events(args.limit),
            as_json=args.as_json,
        )
        return

    if args.command == "context" and args.context_command == "search":
        _emit(
            TramaApiClient(args.api_url).search_memory(
                {
                    "organization_id": args.organization,
                    "project_id": args.project,
                    "agent_id": args.agent,
                    "query": args.query,
                }
            ),
            as_json=args.as_json,
        )

    if args.command == "agent" and args.agent_command == "list":
        _emit(TramaApiClient(args.api_url).list_agents(), as_json=args.as_json)
        return

    if args.command == "knowledge":
        client = TramaApiClient(args.api_url)
        if args.knowledge_command in {"candidates", "review"}:
            value = client.list_memory_candidates(args.organization, args.project)
        elif args.knowledge_command == "validate":
            value = client.validate_memory_candidate(
                args.candidate_id,
                organization_id=args.organization,
                project_id=args.project,
                reviewer=args.reviewer,
            )
        elif args.knowledge_command == "reject":
            value = client.reject_memory_candidate(
                args.candidate_id,
                organization_id=args.organization,
                project_id=args.project,
                reviewer=args.reviewer,
            )
        else:
            if not args.confirm:
                raise SystemExit("confirm required for knowledge promotion")
            value = client.promote(
                PromotionRequest.model_validate(
                    json.loads(Path(args.file).read_text(encoding="utf-8"))
                )
            )
        _emit(value, as_json=args.as_json)
        return

    if args.command == "model" and args.model_command == "list":
        _emit(
            {
                "status": "not_configured",
                "profiles": [],
                "message": "No hay un ModelGatewayPort configurado",
            },
            as_json=args.as_json,
        )
        return

    if args.command == "config" and args.config_command == "get":
        settings = TramaSettings.from_env()
        config = {
            "environment": settings.environment,
            "organization_id": settings.organization_id,
            "state_dir": settings.state_dir,
            "api_host": settings.api_host,
            "api_port": settings.api_port,
            "api_url": settings.api_url,
            "api_token_configured": bool(settings.api_token),
            "gateway_url": settings.gateway_url,
            "gateway_token_configured": bool(settings.gateway_token),
            "coordination_backend": settings.coordination_backend,
            "cccc_executable": settings.cccc_executable,
            "cccc_timeout_seconds": settings.cccc_timeout_seconds,
            "queue_capacity": settings.queue_capacity,
            "max_concurrency": settings.max_concurrency,
            "dispatch_timeout_seconds": settings.dispatch_timeout_seconds,
            "semantica_kg_path": settings.semantica_kg_path,
            "utopia_url": settings.utopia_url,
            "utopia_kb_id": settings.utopia_kb_id,
            "colibri_url": settings.colibri_url,
            "colibri_model": settings.colibri_model,
            "nats_url": settings.nats_url,
            "nats_stream": settings.nats_stream,
            "nats_subject": settings.nats_subject,
            "nats_durable": settings.nats_durable,
            "hermes_executable": settings.hermes_executable,
            "hermes_config_path": settings.hermes_config_path,
        }
        value = config if args.key is None else {args.key: config.get(args.key)}
        _emit(value, as_json=args.as_json)
        return

    if args.command == "hermes":
        settings = TramaSettings.from_env()
        adapter = HermesAdapter(settings.hermes_executable, cwd=getattr(args, "cwd", None))
        if args.hermes_command == "check":
            _emit(adapter.check(), as_json=args.as_json)
        elif args.hermes_command == "configure":
            path = adapter.write_config(Path(args.path).expanduser(), args.api_url)
            _emit({"status": "written", "path": str(path)}, as_json=args.as_json)
        else:
            raise SystemExit(adapter.run(args.hermes_args))


def main() -> None:
    parser = argparse.ArgumentParser(prog="trama")
    subparsers = parser.add_subparsers(dest="command", required=True)
    settings = TramaSettings.from_env()

    api_parser = subparsers.add_parser("api", help="Inicia la API local")
    api_parser.add_argument("--host", default=settings.api_host)
    api_parser.add_argument("--port", type=int, default=settings.api_port)

    mcp_parser = subparsers.add_parser("mcp", help="Inicia o comprueba el servidor MCP")
    mcp_parser.add_argument("--api-url", default=settings.api_url)
    mcp_parser.add_argument("--gateway-url", default=settings.gateway_url)
    mcp_commands = mcp_parser.add_subparsers(dest="mcp_command")
    mcp_check = mcp_commands.add_parser("check")
    _add_api_options(mcp_check, settings)

    _add_control_commands(subparsers, settings)

    tui_parser = subparsers.add_parser("tui", help="Inicia la consola operativa")
    _add_api_options(tui_parser, settings)

    project_validation_parser = subparsers.add_parser("validate-project")
    project_validation_parser.add_argument("path")

    schema_parser = subparsers.add_parser("export-schemas")
    schema_parser.add_argument("destination", type=Path)

    args = parser.parse_args()
    if args.command == "api":
        import uvicorn

        state_store = SqliteStateStore(settings.state_path)
        uvicorn.run(
            create_app(
                coordination=build_coordination(settings),
                context_memory=build_context_memory(settings),
                canonical_knowledge=build_canonical_knowledge(settings),
                state_store=state_store,
                settings=settings,
            ),
            host=args.host,
            port=args.port,
        )
    elif args.command == "mcp":
        if args.mcp_command == "check":
            status = TramaApiClient(args.api_url).get_status()
            _emit(
                {
                    "status": status.get("status", "unknown"),
                    "transport": "stdio",
                    "tools": HermesAdapter.TRAMA_TOOLS,
                },
                as_json=args.as_json,
            )
        else:
            if args.gateway_url:
                run_mcp(
                    args.api_url,
                    gateway_url=args.gateway_url,
                    gateway_token=settings.gateway_token,
                )
            else:
                run_mcp(args.api_url)
    elif args.command in {
        "up",
        "down",
        "status",
        "doctor",
        "project",
        "task",
        "audit",
        "context",
        "hermes",
        "agent",
        "knowledge",
        "model",
        "config",
        "worker",
    }:
        _run_control_command(args)
    elif args.command == "tui":
        from .tui import run_tui

        run_tui(args.api_url)
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
