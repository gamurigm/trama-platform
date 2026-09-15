from pathlib import Path

from trama_platform.project import load_project_manifest


def test_load_project_manifest():
    path = Path(__file__).parents[1] / "examples" / "generador-diccionario.project.yaml"
    manifest = load_project_manifest(path)

    assert manifest.project_id == "generador-diccionario-entidades"
    assert "oracle_audit" in manifest.capabilities
    assert manifest.policies.repositories_read_only is True
