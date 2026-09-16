import pytest
from pydantic import ValidationError

from trama_platform.contracts import OperationEvent, PlanProposal, TaskLog
from trama_platform.observability import sanitize_message


def test_plan_proposal_and_task_log_preserve_lineage():
    proposal = PlanProposal(
        proposal_id="plan-1",
        requirement_id="REQ-1",
        project_id="demo",
        model_profile="codex-planner",
        input_refs=["requirement:REQ-1"],
        phase_ids=["REQ-1:api"],
        task_ids=["REQ-1:api:1"],
        summary="Plan API first",
        correlation_id="corr-1",
    )
    log = TaskLog(
        task_id="REQ-1:api:1",
        phase_id="REQ-1:api",
        requirement_id="REQ-1",
        project_id="demo",
        actor="cccc",
        correlation_id=proposal.correlation_id,
        message="handoff accepted",
        sequence=1,
    )
    event = OperationEvent(
        action="task.dispatch",
        status="accepted",
        project_id="demo",
        task_id=log.task_id,
        phase_id=log.phase_id,
        requirement_id=log.requirement_id,
        correlation_id=log.correlation_id,
    )

    assert proposal.status == "proposed"
    assert log.correlation_id == event.correlation_id


def test_task_log_rejects_empty_message():
    with pytest.raises(ValidationError):
        TaskLog(task_id="task-1", project_id="demo", actor="cccc", message="")


def test_task_log_redacts_tokens_and_bounds_metadata():
    message, metadata = sanitize_message(
        "Authorization: Bearer super-secret",
        {"token": "super-secret", "ok": "visible"},
    )

    assert "super-secret" not in message
    assert metadata["token"] == "[REDACTED]"
    assert metadata["ok"] == "visible"
