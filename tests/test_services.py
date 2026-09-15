import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from trama_platform.services import collect_service_status
from trama_platform.settings import TramaSettings


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            body = b'{"status":"ok"}'
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, format, *args):  # noqa: A003
        return


def _start_health_server():
    server = ThreadingHTTPServer(("127.0.0.1", 0), _HealthHandler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def test_collect_service_status_marks_http_service_ready():
    server, endpoint = _start_health_server()
    try:
        settings = TramaSettings(
            api_url=endpoint,
            ollama_url="http://127.0.0.1:1",
            colibri_url="http://127.0.0.1:1",
            utopia_url="http://127.0.0.1:1",
            colibri_executable="coli-not-installed",
        )

        result = collect_service_status(settings)

        trama = next(service for service in result["services"] if service["id"] == "trama")
        assert trama["status"] == "ready"
        assert trama["kind"] == "http"
        assert trama["endpoint"] == endpoint
    finally:
        server.shutdown()


def test_collect_service_status_tolerates_unavailable_model_services():
    settings = TramaSettings(
        ollama_url="http://127.0.0.1:1",
        colibri_url="http://127.0.0.1:1",
        utopia_url="http://127.0.0.1:1",
        colibri_executable="coli-not-installed",
    )

    result = collect_service_status(settings)
    services = {service["id"]: service for service in result["services"]}

    assert services["ollama"]["status"] == "unavailable"
    assert services["colibri"]["status"] == "unavailable"


def test_collect_service_status_omits_disabled_semantica_and_redacts_secrets(monkeypatch):
    monkeypatch.setenv("UTOPIA_API_TOKEN", "do-not-show-me")
    settings = TramaSettings(
        semantica_enabled=False,
        utopia_url="http://127.0.0.1:1",
        utopia_mcp_url="http://127.0.0.1:1/api/v1/kbs/private/mcp",
    )

    result = collect_service_status(settings)
    serialized = json.dumps(result, ensure_ascii=False)

    assert "semantica" not in {service["id"] for service in result["services"]}
    assert "UTOPIA_API_TOKEN" not in serialized
    assert "do-not-show-me" not in serialized
    assert "Authorization" not in serialized
    assert "headers" not in serialized
