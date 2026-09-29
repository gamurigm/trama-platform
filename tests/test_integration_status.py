from trama_platform.integration_status import check_integration
from trama_platform.settings import TramaSettings


def test_bridge_integration_status_does_not_claim_model_started(monkeypatch):
    calls = []

    class Response:
        status_code = 200
        is_success = True

        def json(self):
            return {"status": "ok"}

    class Client:
        def __init__(self, **kwargs):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return None

        def get(self, url):
            calls.append(url)
            return Response()

    monkeypatch.setattr("trama_platform.integration_status.httpx.Client", Client)
    monkeypatch.setattr("trama_platform.integration_status.shutil.which", lambda name: None)
    settings = TramaSettings(
        coordination_backend="cccc-bridge",
        cccc_bridge_url="http://bridge.test:8091",
        cccc_bridge_token="bridge-test-token",
    )

    report = check_integration("cccc", settings)

    assert calls == ["http://bridge.test:8091/healthz"]
    assert report["status"] == "available"
    assert report["configured"] is True
    assert report["detail"] == (
        "Puente CCCC responde; estado de CCCC y ejecución del modelo sin verificar"
    )
