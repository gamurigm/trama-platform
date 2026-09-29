from pathlib import Path

import yaml


def test_bridge_backend_configuration_is_shared_by_control_plane_and_worker():
    compose_path = Path(__file__).parents[1] / "deploy" / "docker-compose.gateway.yml"
    compose = yaml.safe_load(compose_path.read_text(encoding="utf-8"))

    for service_name in ("control-plane", "python-worker"):
        environment = compose["services"][service_name]["environment"]
        assert (
            environment["TRAMA_COORDINATION_BACKEND"]
            == "${TRAMA_COORDINATION_BACKEND:-memory}"
        )
        assert environment["TRAMA_CCCC_BRIDGE_URL"].startswith("${TRAMA_CCCC_BRIDGE_URL:-")
        assert environment["TRAMA_CCCC_BRIDGE_TOKEN"] == "${TRAMA_CCCC_BRIDGE_TOKEN:-}"
        assert environment["TRAMA_CCCC_BRIDGE_TIMEOUT_SECONDS"].endswith(":-35}")


def test_readme_configures_the_bridge_process_in_its_own_terminal():
    readme_path = Path(__file__).parents[1] / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    bridge_section = readme.split("#### CCCC del host Windows desde el worker Docker", 1)[1]
    host_setup = bridge_section.split(
        "En la terminal PowerShell que ejecutará el puente,", 1
    )[1]
    host_setup = host_setup.split("El comando rechaza", 1)[0]

    assert '$env:TRAMA_CCCC_BRIDGE_TOKEN =' in host_setup
    assert '$env:TRAMA_CCCC_ALLOWED_ACTORS =' in host_setup
    assert "trama cccc-bridge --host" in host_setup
    assert "up -d --build control-plane python-worker" in bridge_section
