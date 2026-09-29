from unittest.mock import patch

from trama_platform.adapters import CcccCliAdapter
from trama_platform.contracts import TaskEnvelope


def test_cccc_adapter_uses_argument_list_and_returns_output():
    task = TaskEnvelope(
        task_id="task-1",
        project_id="demo",
        objective="Inspect repository",
        actor="codex",
        repository="https://example.test/repo",
        branch="main",
        worktree="C:/work/demo",
        acceptance_criteria=["report evidence"],
    )
    completed = type("Completed", (), {"stdout": "delivery-1\n"})()
    with patch("trama_platform.adapters.subprocess.run", return_value=completed) as run:
        delivery = CcccCliAdapter().submit_task(task)

    assert delivery == "delivery-1"
    command = run.call_args.args[0]
    assert command[0] == "cccc"
    assert command[1] == "tracked-send"
    assert "--to" in command
    assert "codex" in command
    assert run.call_args.kwargs["check"] is True


def test_tracked_send_uses_task_id_as_idempotency_key():
    task = TaskEnvelope(
        task_id="task-idempotency-1",
        project_id="demo",
        objective="Inspect repository",
        actor="codex",
        repository="https://example.test/repo",
        branch="main",
        worktree="C:/work/demo",
        acceptance_criteria=["report evidence"],
    )
    completed = type("Completed", (), {"stdout": "delivery-1\n"})()
    with patch("trama_platform.adapters.subprocess.run", return_value=completed) as run:
        CcccCliAdapter().submit_task(task)

    command = run.call_args.args[0]
    key_index = command.index("--idempotency-key")
    assert command[key_index + 1] == "task-idempotency-1"
    assert isinstance(command, list)
