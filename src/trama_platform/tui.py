"""Consola operativa de TRAMA para terminales compatibles con Rich."""

from __future__ import annotations

from typing import Any

from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Vertical
from textual.widgets import DataTable, Footer, Header, Static

from .mcp_server import TramaApiClient


class TramaTuiApp(App[None]):
    """TUI de observabilidad y operación del control plane local."""

    TITLE = "TRAMA Control Plane"
    CSS = """
    Screen {
        background: #101820;
        color: #e8f1f2;
    }
    #status {
        height: 3;
        margin: 1 2;
        padding: 1 2;
        background: #16333a;
        color: #a8f0d0;
    }
    #tasks {
        height: 1fr;
        margin: 0 2 1 2;
    }
    #hint {
        height: 2;
        margin: 0 2;
        color: #9fb4b8;
    }
    """
    BINDINGS = [
        Binding("r", "refresh", "Actualizar"),
        Binding("q", "quit", "Salir"),
    ]

    def __init__(self, client: Any, **kwargs: Any) -> None:
        super().__init__(**kwargs)
        self.client = client

    def compose(self) -> ComposeResult:
        yield Header()
        with Vertical():
            yield Static("Conectando con TRAMA...", id="status")
            yield Static("Tareas activas", id="hint")
            table = DataTable(id="tasks")
            table.add_columns("ID", "Proyecto", "Objetivo")
            yield table
        yield Footer()

    def on_mount(self) -> None:
        self.refresh_data()
        self.set_interval(2, self.refresh_data)

    def action_refresh(self) -> None:
        self.refresh_data()

    def refresh_data(self) -> None:
        status_widget = self.query_one("#status", Static)
        table = self.query_one("#tasks", DataTable)
        try:
            status = self.client.get_status()
            tasks = self.client.list_tasks()
        except Exception as exc:  # noqa: BLE001 - el fallo debe ser visible en la consola
            status_widget.update(f"TRAMA · error · {exc}")
            table.clear()
            return

        status_widget.update(
            "TRAMA · {status} · proyectos={projects} · tareas={tasks}".format(
                status=status.get("status", "unknown"),
                projects=status.get("projects", 0),
                tasks=status.get("tasks", 0),
            )
        )
        table.clear()
        for task in tasks:
            table.add_row(
                str(task.get("task_id", "")),
                str(task.get("project_id", "")),
                str(task.get("objective", "")),
            )


def run_tui(api_url: str) -> None:
    """Inicia la consola operativa contra la API local."""

    TramaTuiApp(TramaApiClient(api_url)).run()
