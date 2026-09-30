"""Run one repeatable admission and worker-visibility experiment against TRAMA."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import platform
import re
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime
from pathlib import Path
from statistics import fmean
from typing import Any

TASK_FIELDS = (
    "task_id",
    "first_status",
    "replay_status",
    "idempotent_replay",
    "gateway_projection_visible",
    "worker_visible",
    "worker_state",
    "admission_ms",
    "replay_ms",
    "delivery_ms",
    "error",
)


def percentile(values: list[float], probability: float) -> float:
    """Return the nearest-rank percentile for a non-empty latency sample."""
    if not values:
        raise ValueError("percentile requires at least one sample")
    if not 0 < probability <= 1:
        raise ValueError("probability must be greater than 0 and at most 1")
    ordered = sorted(values)
    return ordered[math.ceil(probability * len(ordered)) - 1]


def summarize_latencies(values: list[float]) -> dict[str, float | int]:
    if not values:
        return {"count": 0, "mean_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0}
    return {
        "count": len(values),
        "mean_ms": round(fmean(values), 3),
        "p50_ms": round(percentile(values, 0.5), 3),
        "p95_ms": round(percentile(values, 0.95), 3),
        "p99_ms": round(percentile(values, 0.99), 3),
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def request_json(
    url: str,
    *,
    method: str = "GET",
    payload: dict[str, Any] | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 10,
) -> tuple[int, Any]:
    request_headers = {"Accept": "application/json", **(headers or {})}
    body = None
    if payload is not None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request_headers["Content-Type"] = "application/json"
    request = urllib.request.Request(url, data=body, headers=request_headers, method=method)
    try:
        response = urllib.request.urlopen(request, timeout=timeout)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        raw = response.read()
        decoded = json.loads(raw) if raw else None
        return response.status, decoded


def ensure_project(args: argparse.Namespace) -> None:
    project_url = f"{args.api_url.rstrip('/')}/v1/projects/{urllib.parse.quote(args.project_id)}"
    status, existing = request_json(project_url, timeout=args.request_timeout)
    if status == 200:
        if (
            existing.get("organization_id") != args.organization_id
            or existing.get("repository") != args.repository
        ):
            raise ValueError("existing project has a different organization or repository")
        return
    if status != 404:
        raise RuntimeError(f"project lookup failed with HTTP {status}")

    manifest = {
        "schema_version": "1.0",
        "project_id": args.project_id,
        "organization_id": args.organization_id,
        "repository": args.repository,
        "default_branch": "experiment",
        "policies": {
            "repositories_read_only": True,
            "allow_external_writes": False,
            "require_human_approval_for_publish": True,
            "allow_cross_project_context": False,
        },
    }
    status, _ = request_json(
        f"{args.api_url.rstrip('/')}/v1/projects",
        method="POST",
        payload=manifest,
        timeout=args.request_timeout,
    )
    if status != 201:
        raise RuntimeError(f"project registration failed with HTTP {status}")


def make_task(args: argparse.Namespace, task_id: str) -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "task_id": task_id,
        "source": "manual",
        "organization_id": args.organization_id,
        "project_id": args.project_id,
        "repository": args.repository,
        "objective": "Measure durable gateway admission and worker visibility",
        "actor": "thesis-experiment",
        "branch": f"experiment/{args.run_id}",
        "worktree": f"local://thesis/{args.run_id}/{task_id}",
        "read_only": True,
        "state": "accepted",
        "acceptance_criteria": ["task is admitted once", "task is visible in control plane"],
    }


def measure_task(args: argparse.Namespace, sequence: int) -> dict[str, Any]:
    task_id = f"{args.run_id}-{sequence:05d}"
    payload = make_task(args, task_id)
    key = task_id
    gateway = args.gateway_url.rstrip("/")
    api = args.api_url.rstrip("/")
    result: dict[str, Any] = {field: "" for field in TASK_FIELDS}
    result["task_id"] = task_id
    started = time.perf_counter()

    try:
        before = time.perf_counter()
        first_status, first = request_json(
            f"{gateway}/v1/tasks",
            method="POST",
            payload=payload,
            headers={"Idempotency-Key": key},
            timeout=args.request_timeout,
        )
        result["admission_ms"] = round((time.perf_counter() - before) * 1000, 3)
        result["first_status"] = first_status

        before = time.perf_counter()
        replay_status, replay = request_json(
            f"{gateway}/v1/tasks",
            method="POST",
            payload=payload,
            headers={"Idempotency-Key": key},
            timeout=args.request_timeout,
        )
        result["replay_ms"] = round((time.perf_counter() - before) * 1000, 3)
        result["replay_status"] = replay_status
        result["idempotent_replay"] = bool(
            first_status == 202
            and replay_status == 202
            and first.get("task_id") == replay.get("task_id") == task_id
        )

        encoded_task = urllib.parse.quote(task_id, safe="")
        organization = urllib.parse.quote(args.organization_id, safe="")
        projection_status, projection = request_json(
            f"{gateway}/v1/tasks/{encoded_task}?organization_id={organization}",
            timeout=args.request_timeout,
        )
        result["gateway_projection_visible"] = bool(
            projection_status == 200 and projection.get("task_id") == task_id
        )

        deadline = time.perf_counter() + args.delivery_timeout
        while time.perf_counter() < deadline:
            worker_status, worker_task = request_json(
                f"{api}/v1/tasks/{encoded_task}", timeout=args.request_timeout
            )
            if worker_status == 200 and worker_task.get("task_id") == task_id:
                result["worker_visible"] = True
                result["worker_state"] = worker_task.get("state", "")
                result["delivery_ms"] = round((time.perf_counter() - started) * 1000, 3)
                break
            time.sleep(min(0.1, max(0, deadline - time.perf_counter())))
        if not result["worker_visible"]:
            result["error"] = "delivery timeout"
    except (OSError, TimeoutError, ValueError, RuntimeError) as error:
        result["error"] = f"{type(error).__name__}: {error}"
    return result


def git_revision() -> str | None:
    try:
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
            timeout=3,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    return completed.stdout.strip()


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--gateway-url", default="http://127.0.0.1:8080")
    parser.add_argument("--api-url", default="http://127.0.0.1:8090")
    parser.add_argument("--organization-id", default="trama-thesis")
    parser.add_argument("--project-id", default="thesis-experiment")
    parser.add_argument("--repository", default="local://trama-thesis")
    parser.add_argument("--run-id", default=datetime.now(UTC).strftime("run-%Y%m%dT%H%M%S%f"))
    parser.add_argument("--count", type=int, default=100)
    parser.add_argument("--concurrency", type=int, default=5)
    parser.add_argument("--delivery-timeout", type=float, default=30)
    parser.add_argument("--request-timeout", type=float, default=10)
    parser.add_argument("--output-dir", type=Path, default=Path("artifacts/thesis"))
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[a-z0-9][a-z0-9._-]{0,99}", args.project_id):
        parser.error("project-id must be a lowercase TRAMA project identifier")
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]{0,79}", args.run_id):
        parser.error("run-id may contain only letters, digits, dot, underscore and hyphen")
    if not args.organization_id or not args.repository:
        parser.error("organization-id and repository must not be empty")
    if args.count < 1 or args.count > 10000:
        parser.error("count must be between 1 and 10000")
    if args.concurrency < 1 or args.concurrency > min(args.count, 100):
        parser.error("concurrency must be between 1 and min(count, 100)")
    if args.delivery_timeout <= 0 or args.request_timeout <= 0:
        parser.error("timeouts must be positive")
    if (args.output_dir / args.run_id).exists():
        parser.error("run output directory already exists; choose a new run-id")
    return args


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        ensure_project(args)
    except (OSError, TimeoutError, ValueError, RuntimeError) as error:
        print(f"cannot prepare experiment: {error}", file=sys.stderr)
        return 2

    started_at = datetime.now(UTC)
    with ThreadPoolExecutor(max_workers=args.concurrency) as executor:
        futures = [executor.submit(measure_task, args, index) for index in range(args.count)]
        records = [future.result() for future in as_completed(futures)]
    records.sort(key=lambda item: item["task_id"])

    output_dir = args.output_dir / args.run_id
    output_dir.mkdir(parents=True, exist_ok=False)
    csv_path = output_dir / "tasks.csv"
    with csv_path.open("w", newline="", encoding="utf-8") as csv_file:
        writer = csv.DictWriter(csv_file, fieldnames=TASK_FIELDS)
        writer.writeheader()
        writer.writerows(records)

    admission_samples = [float(row["admission_ms"]) for row in records if row["admission_ms"] != ""]
    delivery_samples = [float(row["delivery_ms"]) for row in records if row["delivery_ms"] != ""]
    counts = {
        "http_202": sum(row["first_status"] == 202 for row in records),
        "http_429": sum(row["first_status"] == 429 for row in records),
        "idempotent_replays": sum(row["idempotent_replay"] is True for row in records),
        "gateway_projection_visible": sum(
            row["gateway_projection_visible"] is True for row in records
        ),
        "worker_visible": sum(row["worker_visible"] is True for row in records),
        "errors": sum(bool(row["error"]) for row in records),
    }
    passed = (
        counts["http_202"] == args.count
        and counts["idempotent_replays"] == args.count
        and counts["gateway_projection_visible"] == args.count
        and counts["worker_visible"] == args.count
        and counts["errors"] == 0
    )
    repository_root = Path(__file__).resolve().parents[2]
    source_files = (
        "scripts/thesis/run_distributed_experiment.py",
        "src/trama_platform/runtime.py",
        "docs/tesis/protocolo-experimental.md",
    )
    manifest = {
        "run_id": args.run_id,
        "started_at_utc": started_at.isoformat(),
        "finished_at_utc": datetime.now(UTC).isoformat(),
        "git_revision": git_revision(),
        "source_sha256": {
            name: sha256_file(repository_root / name) for name in source_files
        },
        "host": platform.platform(),
        "python": platform.python_version(),
        "gateway_url": args.gateway_url,
        "api_url": args.api_url,
        "organization_id": args.organization_id,
        "project_id": args.project_id,
        "repository": args.repository,
        "count": args.count,
        "concurrency": args.concurrency,
        "delivery_timeout_seconds": args.delivery_timeout,
        "request_timeout_seconds": args.request_timeout,
        "counts": counts,
        "admission_latency": summarize_latencies(admission_samples),
        "delivery_latency": summarize_latencies(delivery_samples),
        "passed": passed,
        "raw_results": str(csv_path.resolve()),
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(json.dumps(manifest, ensure_ascii=False, indent=2))
    return 0 if passed else 1


if __name__ == "__main__":
    raise SystemExit(main())
