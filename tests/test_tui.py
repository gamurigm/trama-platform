import asyncio


class FakeClient:
    def get_status(self):
        return {"status": "ready", "projects": 1, "tasks": 2}

    def list_tasks(self):
        return [
            {"task_id": "task-1", "project_id": "demo", "objective": "Run tests"},
            {"task_id": "task-2", "project_id": "demo", "objective": "Review docs"},
        ]

    pass


class PlanningClient(FakeClient):
    def get_overview(self, project_id=None):
        return {
            "phases": [{
                "phase_id": "phase-1", "name": "Diseño", "status": "in_progress",
                "completed_tasks": 1, "total_tasks": 2, "progress": 0.5,
            }],
            "queue": [{
                "task_id": "task-1", "objective": "Run tests", "actor": "codex",
                "state": "running", "source": "manual",
            }],
            "agents": [{
                "agent_id": "codex", "active": 1, "completed": 0, "blocked": 0,
            }],
            "queue_status": {"queue_depth": 0, "active_dispatches": 1, "queue_capacity": 10},
            "parallel_groups": [{"phase_ids": ["phase-1"]}],
            "latest_activity": [{"actor": "cccc", "message": "handoff"}],
        }

    def get_task_timeline(self, task_id):
        return [{"sequence": 1, "actor": "cccc", "message": f"timeline {task_id}"}]


def test_tui_renders_control_plane_status_and_tasks():
    asyncio.run(_test_tui_renders_control_plane_status_and_tasks())


async def _test_tui_renders_control_plane_status_and_tasks():
    from trama_platform.tui import TramaTuiApp

    app = TramaTuiApp(FakeClient())

    async with app.run_test() as pilot:
        await pilot.pause()

        assert "ready" in app.query_one("#status").renderable
        table = app.query_one("#tasks")
        assert table.row_count == 2


def test_tui_shows_api_failures_as_visible_state():
    asyncio.run(_test_tui_shows_api_failures_as_visible_state())


async def _test_tui_shows_api_failures_as_visible_state():
    from trama_platform.tui import TramaTuiApp

    class BrokenClient(FakeClient):
        def get_status(self):
            raise RuntimeError("API unavailable")

    app = TramaTuiApp(BrokenClient())

    async with app.run_test() as pilot:
        await pilot.pause()

        assert "API unavailable" in app.query_one("#status").renderable


def test_tui_renders_compact_planning_panels():
    asyncio.run(_test_tui_renders_compact_planning_panels())


async def _test_tui_renders_compact_planning_panels():
    from trama_platform.tui import TramaTuiApp

    app = TramaTuiApp(PlanningClient())
    async with app.run_test() as pilot:
        await pilot.pause()

        assert "Diseño" in app.query_one("#phases").renderable
        assert "codex" in app.query_one("#agents").renderable
        assert app.query_one("#tasks").row_count == 1
        assert "handoff" in app.query_one("#activity").renderable
        assert "#0b1020" in TramaTuiApp.CSS


def test_tui_opens_and_closes_task_timeline():
    asyncio.run(_test_tui_opens_and_closes_task_timeline())


async def _test_tui_opens_and_closes_task_timeline():
    from trama_platform.tui import TramaTuiApp

    app = TramaTuiApp(PlanningClient())
    async with app.run_test() as pilot:
        await pilot.pause()
        await pilot.press("enter")
        assert "timeline task-1" in app.query_one("#detail-content").renderable
        assert "visible" in app.query_one("#detail").classes
        await pilot.press("escape")
        assert "visible" not in app.query_one("#detail").classes
