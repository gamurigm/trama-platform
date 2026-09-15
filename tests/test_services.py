import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

from trama_platform.services import ServiceStatus, collect_service_status
from trama_platform.settings import TramaSettings


class _HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/health":
            body = b'{"status":"ok"}'
        elif self.path == "/api/tags":
            body = b'{"models":[{"name":"qwen3:8b"}]}'
        elif self.path == "/v1/models":
            body = b'{"data":[{"id":"OLMoE-1B-7B-0125-Instruct"}]}'
        else:
            self.send_response(404)
            self.end_headers()
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format, *args):  # noqa: A003
        return


class _MissingModelHandler(_HealthHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/api/tags":
            body = b'{"models":[{"name":"qwen3:4b"}]}'
        elif self.path == "/v1/models":
            body = b'{"data":[{"id":"other-model"}]}'
        else:
            super().do_GET()
            return

        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def _start_server(handler_class=_HealthHandler):
    server = ThreadingHTTPServer(("127.0.0.1", 0), handler_class)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server, f"http://127.0.0.1:{server.server_port}"


def _start_health_server():
    return _start_server()


def _start_mcp_server(status_code=200, response=None):
    requests = []

    class _McpHandler(BaseHTTPRequestHandler):
        def do_POST(self):  # noqa: N802
            length = int(self.headers.get("Content-Length", "0"))
            requests.append(
                {
                    "path": self.path,
                    "headers": dict(self.headers.items()),
                    "body": json.loads(self.rfile.read(length)),
                }
            )
            body = json.dumps(
                response
                or {
                    "jsonrpc": "2.0",
                    "id": 1,
                    "result": {
                        "protocolVersion": "2025-03-26",
                        "capabilities": {},
                        "serverInfo": {"name": "utopia", "version": "test"},
                    },
                }
            ).encode("utf-8")
            self.send_response(status_code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, format, *args):  # noqa: A003
            return

    server, endpoint = _start_server(_McpHandler)
    return server, f"{endpoint}/api/v1/kbs/local/mcp", requests


def test_collect_service_status_marks_configured_models_ready_when_listed():
    server, endpoint = _start_server()
    try:
        settings = TramaSettings(
            api_url="http://127.0.0.1:1",
            ollama_url=endpoint,
            colibri_url=endpoint,
            utopia_url="http://127.0.0.1:1",
        )

        result = collect_service_status(settings)
        services = {service["id"]: service for service in result["services"]}

        assert services["ollama"]["status"] == "ready"
        assert services["colibri"]["status"] == "ready"
    finally:
        server.shutdown()


def test_collect_service_status_keeps_model_services_unavailable_when_model_missing():
    server, endpoint = _start_server(_MissingModelHandler)
    try:
        settings = TramaSettings(
            api_url="http://127.0.0.1:1",
            ollama_url=endpoint,
            colibri_url=endpoint,
            utopia_url="http://127.0.0.1:1",
        )

        result = collect_service_status(settings)
        services = {service["id"]: service for service in result["services"]}

        assert services["ollama"]["status"] == "unavailable"
        assert services["colibri"]["status"] == "unavailable"
    finally:
        server.shutdown()


def test_service_status_sanitizes_unsafe_endpoint_components():
    status = ServiceStatus(
        id="utopia",
        status="ready",
        kind="mcp",
        endpoint="http://user:password@127.0.0.1:1516/mcp?token=secret#fragment",
        message="ok",
    )

    assert status.endpoint == "http://127.0.0.1:1516/mcp"
    assert status.as_dict()["endpoint"] == "http://127.0.0.1:1516/mcp"


def test_collect_service_status_initializes_configured_utopia_mcp_without_auth_header():
    server, mcp_endpoint, requests = _start_mcp_server()
    try:
        settings = TramaSettings(
            api_url="http://127.0.0.1:1",
            ollama_url="http://127.0.0.1:1",
            colibri_url="http://127.0.0.1:1",
            utopia_url="http://127.0.0.1:1",
            utopia_mcp_url=mcp_endpoint,
        )

        result = collect_service_status(settings)
        utopia = next(service for service in result["services"] if service["id"] == "utopia")

        assert utopia["status"] == "ready"
        assert utopia["kind"] == "mcp"
        assert utopia["endpoint"] == mcp_endpoint
        assert requests[0]["body"]["method"] == "initialize"
        assert "Authorization" not in requests[0]["headers"]
    finally:
        server.shutdown()


def test_collect_service_status_does_not_mark_utopia_mcp_ready_when_unauthorized():
    server, mcp_endpoint, _ = _start_mcp_server(
        status_code=401,
        response={"jsonrpc": "2.0", "id": 1, "error": {"code": -32001}},
    )
    try:
        settings = TramaSettings(
            api_url="http://127.0.0.1:1",
            ollama_url="http://127.0.0.1:1",
            colibri_url="http://127.0.0.1:1",
            utopia_url="http://127.0.0.1:1",
            utopia_mcp_url=mcp_endpoint,
        )

        result = collect_service_status(settings)
        utopia = next(service for service in result["services"] if service["id"] == "utopia")

        assert utopia["status"] == "unavailable"
    finally:
        server.shutdown()


def test_collect_service_status_does_not_mark_utopia_mcp_ready_when_unreachable():
    settings = TramaSettings(
        api_url="http://127.0.0.1:1",
        ollama_url="http://127.0.0.1:1",
        colibri_url="http://127.0.0.1:1",
        utopia_url="http://127.0.0.1:1",
        utopia_mcp_url="http://127.0.0.1:1/api/v1/kbs/local/mcp",
    )

    result = collect_service_status(settings)
    utopia = next(service for service in result["services"] if service["id"] == "utopia")

    assert utopia["status"] == "unavailable"


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
