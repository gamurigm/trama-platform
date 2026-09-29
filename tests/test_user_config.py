from dataclasses import replace

import pytest
import yaml
from fastapi.testclient import TestClient

from trama_platform.api import create_app
from trama_platform.hermes import HermesAdapter
from trama_platform.settings import TramaSettings
from trama_platform.user_config import UserConfigStore, config_snapshot


class Vault:
    def __init__(self):
        self.values = {}

    def get(self, name):
        return self.values.get(name)

    def has(self, name):
        return bool(self.get(name))

    def set(self, name, value):
        if name not in {"api_token", "gateway_token", "utopia_token"}:
            raise ValueError("Nombre de credencial no permitido")
        self.values[name] = value

    def delete(self, name):
        self.values.pop(name, None)


@pytest.fixture
def stores(tmp_path, monkeypatch):
    store, vault = UserConfigStore(tmp_path / "user" / "config.json"), Vault()
    monkeypatch.setattr("trama_platform.config_contracts.UserConfigStore", lambda: store)
    monkeypatch.setattr("trama_platform.config_contracts.CredentialStore", lambda: vault)
    for name in (
        "TRAMA_MAX_CONCURRENCY",
        "TRAMA_API_TOKEN",
        "TRAMA_GATEWAY_TOKEN",
        "TRAMA_UTOPIA_TOKEN",
    ):
        monkeypatch.delenv(name, raising=False)
    return store, vault


def test_config_precedence_restart_and_reset(stores, monkeypatch):
    store, vault = stores
    active = TramaSettings()
    store.update({"max_concurrency": 2})
    assert TramaSettings.from_env(store=store, vault=vault).max_concurrency == 2
    snapshot = config_snapshot(active, store, vault)
    assert snapshot["restart_required"]
    monkeypatch.setenv("TRAMA_MAX_CONCURRENCY", "7")
    assert TramaSettings.from_env(store=store, vault=vault).max_concurrency == 7
    item = next(
        x
        for x in config_snapshot(active, store, vault)["settings"]
        if x["name"] == "max_concurrency"
    )
    assert item["source"] == "environment"
    store.update({"max_concurrency": None})
    assert "max_concurrency" not in store.read()


@pytest.mark.parametrize(
    "values",
    [
        {"api_token": "private"},
        {"nats_url": "nats://user:private@localhost:4222"},
        {"api_host": "0.0.0.0"},
        {"max_concurrency": 0},
        {"unknown": "x"},
    ],
)
def test_rejected_settings_do_not_create_file(stores, values):
    store, _ = stores
    with pytest.raises(ValueError):
        store.update(values)
    assert not store.path.exists()


def test_secret_write_read_clear_and_validation_never_echo_value(stores):
    store, vault = stores
    sentinel = "PRIVATE-TEST-VALUE-7924"
    with TestClient(create_app(settings=TramaSettings())) as client:
        result = client.put("/v1/config/secrets/api_token", json={"value": sentinel})
        assert result.status_code == 200
        assert vault.get("api_token") == sentinel
        assert sentinel not in result.text
        for endpoint in ("/v1/config", "/v1/config/secrets"):
            response = client.get(endpoint)
            assert response.status_code == 200
            assert sentinel not in response.text
        malformed = client.put("/v1/config/secrets/api_token", json={"value": {"raw": sentinel}})
        assert malformed.status_code == 422
        assert sentinel not in malformed.text
        assert not store.path.exists()
        assert client.delete("/v1/config/secrets/api_token").status_code == 200
        assert vault.get("api_token") is None


def test_config_requires_active_bearer_and_rejects_browser_writes(stores):
    with TestClient(
        create_app(settings=replace(TramaSettings(), api_token="active-test"))
    ) as client:
        assert client.put("/v1/config", json={"values": {"max_concurrency": 2}}).status_code == 401
        assert (
            client.put(
                "/v1/config",
                headers={"Authorization": "Bearer active-test", "Origin": "https://other.test"},
                json={"values": {"max_concurrency": 2}},
            ).status_code
            == 403
        )
        assert (
            client.put(
                "/v1/config",
                headers={"Authorization": "Bearer active-test"},
                json={"values": {"max_concurrency": 2}},
            ).status_code
            == 200
        )


def test_app_root_preserves_database_path(tmp_path, monkeypatch):
    monkeypatch.setenv("TRAMA_APP_ROOT", str(tmp_path))
    assert TramaSettings().state_path == tmp_path / "artifacts" / "state" / "trama.db"


def test_hermes_merge_preserves_other_servers_and_requires_manual_approval(tmp_path):
    path = tmp_path / "hermes.yaml"
    path.write_text(
        yaml.safe_dump(
            {
                "model": "local-model",
                "mcp_servers": {"other": {"command": "other"}},
                "approvals": {"custom": True},
            }
        )
    )
    HermesAdapter(cwd=tmp_path).write_config(path, "http://127.0.0.1:8090")
    saved = yaml.safe_load(path.read_text())
    assert saved["model"] == "local-model"
    assert saved["mcp_servers"]["other"] == {"command": "other"}
    assert saved["approvals"]["custom"] is True
    assert saved["approvals"]["mode"] == "manual"
    assert str(tmp_path.resolve()) in saved["mcp_servers"]["trama"]["args"]


@pytest.mark.parametrize("token", ["contraseña", "line\nbreak", "space token", "bad\x00token"])
def test_bearer_tokens_reject_non_header_text_before_vault_access(token, monkeypatch):
    from trama_platform.credential_store import CredentialStore

    vault = CredentialStore()
    monkeypatch.setattr(
        vault, "_backend", lambda: pytest.fail("Invalid token reached the OS vault")
    )
    with pytest.raises(ValueError):
        vault.set("api_token", token)


def test_mcp_inventory_does_not_claim_a_live_transport_connection():
    from trama_platform.integration_status import check_integration

    report = check_integration("mcp", TramaSettings())
    assert report["tools"]
    assert report["status"] == "available"
