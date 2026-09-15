from pathlib import Path

from trama_platform.lifecycle import GatewaySupervisor


def test_supervisor_starts_api_and_records_pid(tmp_path: Path):
    launched = []

    class FakeProcess:
        pid = 4321

    def fake_popen(command, **kwargs):
        launched.append((command, kwargs))
        return FakeProcess()

    supervisor = GatewaySupervisor(
        state_dir=tmp_path,
        command=["python", "-m", "trama_platform", "api"],
        popen_factory=fake_popen,
        is_running=lambda pid: pid == 4321,
    )

    result = supervisor.start()

    assert result == {"status": "started", "pid": 4321}
    assert supervisor.pid_path.read_text(encoding="utf-8") == "4321"
    assert launched[0][0] == ["python", "-m", "trama_platform", "api"]


def test_supervisor_stops_only_the_recorded_process(tmp_path: Path):
    stopped: list[int] = []
    supervisor = GatewaySupervisor(
        state_dir=tmp_path,
        is_running=lambda pid: pid == 4321,
        terminate=lambda pid: stopped.append(pid),
    )
    supervisor.pid_path.write_text("4321", encoding="utf-8")

    result = supervisor.stop()

    assert result == {"status": "stopped", "pid": 4321}
    assert stopped == [4321]
    assert not supervisor.pid_path.exists()
