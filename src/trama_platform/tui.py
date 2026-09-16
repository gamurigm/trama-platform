"""Consola operativa compacta de TRAMA para terminales compatibles con Rich."""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Horizontal, Vertical
from textual.widgets import DataTable, Footer, Header, Static

from .mcp_server import TramaApiClient


class TramaTuiApp(App[None]):
    """Radar compacto de fases, cola CCCC y actividad operativa."""

    TITLE = "TRAMA Control Plane"
    CSS = """
    Screen { background: #0b1020; color: #eee7ff; }
    Header { background: #17132b; color: #ffad66; }
    #status { height: 2; margin: 0 1; padding: 0 1; color: #ffad66; }
    #dashboard { height: 1fr; padding: 0 1; }
    .column { width: 1fr; height: 1fr; padding: 0 1; }
    .panel { border: round #3b2a63; margin: 0 0 1 0; padding: 0 1; background: #11172a; }
    .panel-title { height: 1; color: #ffb454; text-style: bold; }
    #phases { height: 1fr; }
    #activity { height: 8; }
    #agents { height: 8; }
    #tasks { height: 1fr; }
    #detail { height: 10; display: none; }
    #detail.visible { display: block; }
    DataTable { scrollbar-size: 1 1; background: #11172a; color: #eee7ff; }
    Footer { background: #17132b; color: #9b6cff; }
    """
    BINDINGS = [
        Binding("r", "refresh", "Actualizar"),
        Binding("enter", "open_detail", "Detalle"),
        Binding("escape", "close_detail", "Volver"),
        Binding("q", "quit", "Salir"),
    ]

    def __init__(self, client: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.client = client
        self._task_ids: list[str] = []

    def compose(self) -> ComposeResult:
        yield Header()
        yield Static("TRAMA | conectando...", id="status")
        with Horizontal(id="dashboard"):
            with Vertical(classes="column"):
                with Vertical(classes="panel"):
                    yield Static("FASES", classes="panel-title")
                    yield Static("Sin datos", id="phases")
                with Vertical(classes="panel"):
                    yield Static("ÚLTIMA ACTIVIDAD", classes="panel-title")
                    yield Static("Sin actividad", id="activity")
            with Vertical(classes="column"):
                with Vertical(classes="panel"):
                    yield Static("COLA CCCC / APROBACIÓN", classes="panel-title")
                    table = DataTable(id="tasks", cursor_type="row")
                    table.add_columns("", "Tarea", "Agente", "Origen")
                    yield table
                with Vertical(classes="panel"):
                    yield Static("ESPECIALISTAS CCCC", classes="panel-title")
                    yield Static("Sin datos", id="agents")
        with Vertical(classes="panel", id="detail"):
            yield Static("TIMELINE DE TAREA", classes="panel-title")
            yield Static("Selecciona una tarea y pulsa Enter", id="detail-content")
        yield Footer()

    def on_mount(self) -> None:
        self.query_one("#tasks", DataTable).focus()
        self.refresh_data()
        self.set_interval(2, self.refresh_data)

    def action_refresh(self) -> None:
        self.refresh_data()

    def action_open_detail(self) -> None:
        table = self.query_one("#tasks", DataTable)
        if table.cursor_row < 0 or table.cursor_row >= len(self._task_ids):
            return
        task_id = self._task_ids[table.cursor_row]
        try:
            timeline_method = getattr(self.client, "get_task_timeline", None)
            timeline = timeline_method(task_id) if callable(timeline_method) else []
            detail = self.query_one("#detail", Vertical)
            self.query_one("#detail-content", Static).update(
                self._render_timeline(task_id, timeline)
            )
            detail.add_class("visible")
        except Exception as exc:  # noqa: BLE001 - el detalle debe ser visible
            self.query_one("#detail-content", Static).update(f"[#ef6a4a]error: {exc}[/#ef6a4a]")

    def action_close_detail(self) -> None:
        self.query_one("#detail", Vertical).remove_class("visible")

    def on_data_table_row_selected(self, _: DataTable.RowSelected) -> None:
        self.action_open_detail()

    @staticmethod
    def _bar(progress: float, width: int = 18) -> str:
        filled = max(0, min(width, round(progress * width)))
        return "━" * filled + "─" * (width - filled)

    def refresh_data(self) -> None:
        status_widget = self.query_one("#status", Static)
        phases_widget = self.query_one("#phases", Static)
        agents_widget = self.query_one("#agents", Static)
        table = self.query_one("#tasks", DataTable)
        try:
            status = self.client.get_status()
            overview_method = getattr(self.client, "get_overview", None)
            overview = overview_method() if callable(overview_method) else {}
            tasks = overview.get("queue") or self.client.list_tasks()
            phases = overview.get("phases", [])
            agents = overview.get("agents", [])
            if not agents:
                list_agents = getattr(self.client, "list_agents", None)
                agents = list_agents() if callable(list_agents) else []
        except Exception as exc:  # noqa: BLE001 - el fallo debe ser visible en la consola
            status_widget.update(f"TRAMA | error | {exc}")
            phases_widget.update("[#ffad66]! sin datos de fases")
            agents_widget.update("[#ffad66]! sin datos de agentes")
            table.clear()
            return

        queue = status.get("queue_depth", 0)
        active = status.get("active_dispatches", 0)
        status_widget.update(
            "TRAMA | {state} | proyectos={projects} | cola={queue} | ejecutando={active}".format(
                state=status.get("status", "unknown"),
                projects=status.get("projects", 0),
                queue=queue,
                active=active,
            )
        )
        phases_widget.update(self._render_phases(phases, overview.get("parallel_groups", [])))
        agents_widget.update(self._render_agents(agents))
        self.query_one("#activity", Static).update(
            self._render_activity(overview.get("latest_activity", []))
        )
        table.clear()
        self._task_ids = []
        for task in tasks:
            state = str(task.get("state", "?"))
            marker = {
                "running": "[#4f8cff]›[/#4f8cff]",
                "blocked": "[#ef6a4a]![/#ef6a4a]",
                "succeeded": "[#ffc857]✓[/#ffc857]",
            }.get(state, "[#9b6cff]○[/#9b6cff]")
            table.add_row(
                marker,
                str(task.get("objective", task.get("task_id", ""))),
                str(task.get("actor", "-")),
                str(task.get("source", "manual")),
            )
            self._task_ids.append(str(task.get("task_id", "")))

    def _render_phases(
        self,
        phases: list[dict[str, Any]],
        parallel_groups: list[dict[str, Any]] | None = None,
    ) -> str:
        if not phases:
            return "[dim]sin fases configuradas[/dim]"
        lines: list[str] = []
        group_by_phase = {
            phase_id: index + 1
            for index, group in enumerate(parallel_groups or [])
            for phase_id in group.get("phase_ids", [])
        }
        for phase in phases:
            status = str(phase.get("status", "planned"))
            style = {
                "completed": "#ffc857",
                "blocked": "#ef6a4a",
                "in_progress": "#4f8cff",
                "ready": "#9b6cff",
            }.get(status, "#756b91")
            progress = float(phase.get("progress", 0.0))
            counts = f"{phase.get('completed_tasks', 0)}/{phase.get('total_tasks', 0)}"
            name = phase.get("name", phase.get("phase_id", "fase"))
            group = group_by_phase.get(phase.get("phase_id"), "·")
            lines.append(
                f"[#9b6cff]{group}[/#9b6cff] "
                f"[{style}]{self._bar(progress)}[/{style}] {name} {counts}"
            )
        return "\n".join(lines)

    @staticmethod
    def _render_activity(activity: list[dict[str, Any]]) -> str:
        if not activity:
            return "[dim]sin actividad reciente[/dim]"
        lines = []
        for item in activity[-5:]:
            actor = item.get("actor", "system")
            label = item.get("action") or item.get("message") or item.get("entry_id", "evento")
            lines.append(f"[#ffad66]{actor}[/#ffad66] {label}")
        return "\n".join(lines)

    @staticmethod
    def _render_timeline(task_id: str, timeline: list[dict[str, Any]]) -> str:
        if not timeline:
            return f"[#9b6cff]{task_id}[/#9b6cff]\n[dim]sin eventos ni logs[/dim]"
        lines = [f"[#ffb454]{task_id}[/#ffb454]"]
        for item in timeline[-8:]:
            label = item.get("action") or item.get("message") or "evento"
            actor = item.get("actor", "system")
            lines.append(f"[#9b6cff]{item.get('sequence', '·'):>2}[/#9b6cff] {actor}: {label}")
        return "\n".join(lines)

    @staticmethod
    def _render_agents(agents: list[dict[str, Any]]) -> str:
        if not agents:
            return "[dim]sin especialistas asignados[/dim]"
        lines = []
        for agent in agents:
            active = agent.get("active", 0)
            total = agent.get("tasks", 0)
            completed = agent.get("completed", 0)
            lines.append(
                f"[#c084fc]{agent.get('agent_id', '-')}[/#c084fc]  "
                f"[#ffad66]›{active}[/#ffad66]  "
                f"[#ffc857]✓{completed}[/#ffc857]  total={total}"
            )
        return "\n".join(lines)


def run_tui(api_url: str) -> None:
    """Inicia la consola operativa contra la API local."""

    TramaTuiApp(TramaApiClient(api_url)).run()
