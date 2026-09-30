import hashlib

import pytest

from scripts.thesis.run_distributed_experiment import (
    auth_headers,
    parse_args,
    percentile,
    sha256_file,
    summarize_latencies,
)


def test_auth_headers_supply_control_plane_context_and_optional_gateway_token(monkeypatch):
    monkeypatch.setenv("TRAMA_CONTROL_PLANE_INTERNAL_TOKEN", "internal-test-token")
    monkeypatch.setenv("TRAMA_GATEWAY_SERVICE_ACCOUNT_TOKEN", "gateway-test-token")
    args = parse_args([
        "--run-id", "header-check",
        "--organization-id", "org-test",
        "--project-id", "project-test",
    ])

    gateway, api = auth_headers(args)

    assert gateway == {"Authorization": "Bearer gateway-test-token"}
    assert api == {
        "X-TRAMA-Internal-Token": "internal-test-token",
        "X-Organization-ID": "org-test",
        "X-Project-ID": "project-test",
        "X-Actor-ID": "thesis-experiment",
    }


def test_auth_headers_require_internal_token(monkeypatch):
    monkeypatch.delenv("TRAMA_CONTROL_PLANE_INTERNAL_TOKEN", raising=False)
    args = parse_args(["--run-id", "missing-token"])
    with pytest.raises(ValueError, match="TRAMA_CONTROL_PLANE_INTERNAL_TOKEN"):
        auth_headers(args)


def test_percentile_uses_nearest_rank_for_latency_samples():
    assert percentile([8.0, 1.0, 4.0, 2.0], 0.5) == 2.0
    assert percentile([8.0, 1.0, 4.0, 2.0], 0.95) == 8.0


def test_percentile_rejects_invalid_probability_or_empty_samples():
    with pytest.raises(ValueError):
        percentile([], 0.5)
    with pytest.raises(ValueError):
        percentile([1.0], 1.1)


def test_latency_summary_reports_stable_sample_statistics():
    assert summarize_latencies([1.0, 2.0, 3.0, 4.0]) == {
        "count": 4,
        "mean_ms": 2.5,
        "p50_ms": 2.0,
        "p95_ms": 4.0,
        "p99_ms": 4.0,
    }


def test_sha256_file_identifies_the_exact_experiment_source(tmp_path):
    source = tmp_path / "experiment.py"
    source.write_bytes(b"trama experiment\n")

    assert sha256_file(source) == hashlib.sha256(b"trama experiment\n").hexdigest()


def test_experiment_refuses_to_reuse_an_existing_run_directory(tmp_path):
    (tmp_path / "existing-run").mkdir()

    with pytest.raises(SystemExit):
        parse_args(["--run-id", "existing-run", "--output-dir", str(tmp_path)])
