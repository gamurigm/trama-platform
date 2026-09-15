import asyncio


class FakeClient:
    def get_status(self):
        return {"status": "ready", "projects": 1, "tasks": 2}

    def list_tasks(self):
        return [
            {"task_id": "task-1", "project_id": "demo", "objective": "Run tests"},
            {"task_id": "task-2", "project_id": "demo", "objective": "Review docs"},
        ]


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
