# CCCC Host Bridge Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Route admitted TRAMA tasks from the Docker worker to a Windows CCCC actor through an authenticated local bridge, preserve result forwarding, and measure dispatch latency.

**Architecture:** Keep PostgreSQL, the transactional outbox, JetStream, the Python worker, and its SQLite state in Docker. Run a small FastAPI bridge on the Windows host; the worker's `CoordinationPort` client calls it for task submissions and results, while the bridge invokes only fixed CCCC CLI operations. Correlate timings by task ID and report model-start latency only when CCCC exposes a verifiable event.

**Tech Stack:** Go gateway and existing outbox, NATS JetStream, Python 3.12+, FastAPI, httpx, Pydantic, CCCC CLI, Docker Compose through WSL.

**Spec:** `docs/superpowers/specs/2026-09-28-cccc-host-bridge-design.md`

## Global Constraints

- Preserve the PostgreSQL outbox and NATS JetStream admission path.
- Use a locally configured bearer secret; never commit it or put it in task payloads.
- Invoke CCCC with argument arrays, never a shell, and never accept arbitrary CLI arguments from HTTP requests.
- Use the task ID as the CCCC task idempotency key.
- Keep task recipients allowlisted and the result recipient fixed in local bridge configuration.
- Do not log task bodies, credentials, or model output.
- A successful `tracked-send` acknowledgement is not evidence that model inference started.
- The latency probe must run no commands and make no repository changes.
- Run Docker and Compose commands through WSL; do not install global Docker or Kubernetes tools.

## Review Focus

- Missing or invalid bearer token: reject before invoking CCCC; covered in bridge auth tests.
- Malformed task/result body: return validation error without invoking CCCC; covered in endpoint tests.
- Unapproved task actor or result recipient: reject/force configured recipient without building arbitrary CLI arguments; covered in bridge tests.
- Re-delivered task ID: invoke CCCC with the same idempotency key; covered in bridge and adapter tests.
- CCCC timeout/nonzero exit or unreachable bridge: report failed dispatch, never success; covered in bridge/client tests and smoke failure-path review.
- CCCC reports only acceptance: latency report must stop at CCCC acknowledgement unless a verifiable runtime event exists; covered in probe report review.

---

### Task 1: Add bridge configuration and a CCCC bridge client

**Files:**
- Modify: `src/trama_platform/settings.py`
- Modify: `src/trama_platform/credential_store.py`
- Modify: `src/trama_platform/user_config.py`
- Create: `src/trama_platform/cccc_bridge_client.py`
- Test: `tests/test_settings.py`
- Test: `tests/test_user_config.py`
- Test: `tests/test_cccc_bridge_client.py`

**Interfaces:**
- `CcccBridgeCoordination(base_url: str, token: str, timeout_seconds: float)` implements `CoordinationPort`.
- `submit_task(task: TaskEnvelope) -> str` POSTs the task to `/v1/tasks` and returns the bridge's tracking ID.
- `record_result(result: AgentResult) -> None` POSTs the result to `/v1/results` and raises on a non-success response.
- Add backend value `cccc-bridge`; keep `memory` as the default and retain existing direct `cccc` behavior.
- Add bridge URL and timeout settings plus a secret bridge token. Add host-only bridge bind/port, allowed actor list, and fixed result recipient settings for the bridge process.

- [ ] **Step 1: Write failing settings and client tests**

  Add `test_cccc_bridge_backend_settings_validate_url_and_token`, `test_cccc_bridge_token_is_redacted`, `test_cccc_bridge_actor_allowlist_is_parsed`, `test_bridge_client_submit_task_sends_bearer_and_returns_tracking_id`, `test_bridge_client_record_result_sends_agent_result`, and `test_bridge_client_propagates_http_errors_and_timeouts`. Assert valid JSON bodies, exact bearer header, returned tracking ID, and raised errors on non-2xx/timeout.

- [ ] **Step 2: Run focused tests and confirm the new expectations fail**

  Run: `.\.venv\Scripts\python.exe -m pytest tests/test_settings.py tests/test_user_config.py tests/test_cccc_bridge_client.py -q`
  Expected: failures for bridge settings and the missing client module/interface.

- [ ] **Step 3: Implement validated bridge settings and `CcccBridgeCoordination`**

  Add only bridge configuration needed by the worker/client and host process. Register the bridge token as secret material; never include it in `config get` output. Use the existing `httpx` dependency, bearer auth, JSON serialization from Pydantic, and explicit request timeouts.

- [ ] **Step 4: Run focused tests**

  Run: `.\.venv\Scripts\python.exe -m pytest tests/test_settings.py tests/test_user_config.py tests/test_cccc_bridge_client.py -q`
  Expected: PASS; invalid URLs or missing token fail at configuration/request boundaries without leaking the token.

- [ ] **Step 5: Commit the task**

  ```bash
  git add src/trama_platform/settings.py src/trama_platform/credential_store.py src/trama_platform/user_config.py src/trama_platform/cccc_bridge_client.py tests/test_settings.py tests/test_user_config.py tests/test_cccc_bridge_client.py
  git commit -m "feat: add CCCC bridge client configuration"
  ```

### Task 2: Implement the authenticated Windows CCCC bridge

**Files:**
- Create: `src/trama_platform/cccc_bridge.py`
- Modify: `src/trama_platform/adapters.py`
- Modify: `src/trama_platform/cli.py`
- Test: `tests/test_cccc_bridge.py`
- Test: `tests/test_adapters.py`

**Interfaces:**
- `create_cccc_bridge_app(settings: TramaSettings, cccc: CoordinationPort | None = None) -> FastAPI` creates the host service.
- `GET /healthz` returns only a minimal readiness status.
- `POST /v1/tasks` accepts a validated `TaskEnvelope`, authenticates the bearer token, enforces the configured actor allowlist, and returns a tracking ID.
- `POST /v1/results` accepts a validated `AgentResult`, authenticates the bearer token, and always forwards it to the configured result recipient.
- Extend `CcccCliAdapter.submit_task` to pass `--idempotency-key <task_id>`; keep invocation via `subprocess` argument arrays.

- [ ] **Step 1: Write failing bridge and adapter tests**

  Add `test_task_endpoint_rejects_missing_or_invalid_token_before_cccc`, `test_task_endpoint_rejects_invalid_envelope_and_actor`, `test_task_endpoint_calls_submit_task_for_allowlisted_actor`, `test_result_endpoint_uses_fixed_recipient`, `test_tracked_send_uses_task_id_as_idempotency_key`, and `test_cccc_timeout_returns_sanitized_error`. Assert rejected task requests make zero CCCC calls, accepted requests make one call, and subprocess arguments contain no shell string or request-controlled flags.

- [ ] **Step 2: Run focused tests and confirm they fail**

  Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cccc_bridge.py tests/test_adapters.py -q`
  Expected: bridge module/routes are missing and CCCC invocation lacks the idempotency key.

- [ ] **Step 3: Implement the FastAPI bridge and safe CCCC calls**

  Compare bearer tokens with constant-time comparison. Do not accept CLI paths, flags, command strings, or arbitrary recipients from requests. Use the existing `CcccCliAdapter` for fixed `tracked-send` and `send` operations. Return sanitized client errors and server errors.

- [ ] **Step 4: Add the `trama cccc-bridge` command and run focused tests**

  Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cccc_bridge.py tests/test_adapters.py -q`
  Expected: PASS, including that rejected requests never invoke CCCC and result recipients cannot be chosen by the request.

- [ ] **Step 5: Commit the task**

  ```bash
  git add src/trama_platform/cccc_bridge.py src/trama_platform/adapters.py src/trama_platform/cli.py tests/test_cccc_bridge.py tests/test_adapters.py
  git commit -m "feat: add authenticated CCCC host bridge"
  ```

### Task 3: Wire the selected backend into API and NATS worker lifecycles

**Files:**
- Modify: `src/trama_platform/cli.py`
- Modify: `src/trama_platform/worker.py`
- Modify: `src/trama_platform/runtime.py`
- Modify: `src/trama_platform/integration_status.py`
- Test: `tests/test_cli_gateway.py`
- Test: `tests/test_worker.py`
- Test: `tests/test_runtime.py`
- Test: `tests/test_integration_status.py`

**Interfaces:**
- `build_coordination(settings: TramaSettings) -> CoordinationPort | None` returns `None` for memory, the existing adapter for `cccc`, and `CcccBridgeCoordination` for `cccc-bridge`.
- `serve_task_worker` passes that coordination port into its owned `TramaRuntime`.
- Runtime status identifies the selected coordination implementation; shutdown closes any bridge HTTP client it owns.

- [ ] **Step 1: Write failing worker/backend/lifecycle tests**

  Add `test_build_coordination_selects_bridge_backend`, `test_worker_passes_configured_coordination_to_runtime`, `test_memory_backend_remains_default`, `test_unreachable_bridge_marks_dispatch_failed`, `test_runtime_close_closes_coordination_once`, and `test_bridge_integration_status_does_not_claim_model_started`. Assert the selected adapter type, failed task state on HTTP failure, one cleanup call, and truthful readiness text.

- [ ] **Step 2: Run focused tests and confirm they fail**

  Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cli_gateway.py tests/test_worker.py tests/test_runtime.py tests/test_integration_status.py -q`
  Expected: worker/backend selection and adapter lifecycle expectations fail.

- [ ] **Step 3: Wire the backend and close its client on shutdown**

  Reuse `build_coordination` for the API and worker. Add deterministic cleanup for an owned bridge HTTP client through the runtime shutdown path. Keep NATS acknowledgement behavior unchanged: a task is acknowledged after durable inbox claim and local task persistence/enqueue, while CCCC submission success/failure is recorded by the dispatcher.

- [ ] **Step 4: Run focused tests**

  Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cli_gateway.py tests/test_worker.py tests/test_runtime.py tests/test_integration_status.py -q`
  Expected: PASS; an unreachable bridge yields a failed dispatch, not a successful CCCC status.

- [ ] **Step 5: Commit the task**

  ```bash
  git add src/trama_platform/cli.py src/trama_platform/worker.py src/trama_platform/runtime.py src/trama_platform/integration_status.py tests/test_cli_gateway.py tests/test_worker.py tests/test_runtime.py tests/test_integration_status.py
  git commit -m "feat: route gateway worker tasks to CCCC bridge"
  ```

### Task 4: Configure Compose, observability, and operator instructions

**Files:**
- Modify: `deploy/docker-compose.gateway.yml`
- Modify: `README.md`
- Modify: `docs/ARQUITECTURA.md`
- Modify: `src/trama_platform/cccc_bridge_client.py`
- Test: `tests/test_cccc_bridge_client.py`

**Interfaces:**
- Python worker receives bridge backend, bridge URL, bearer token, and timeout through environment variables.
- The bridge client emits structured task-correlated request start/completion logs with `dispatch_duration_ms` and tracking ID; it never logs payloads or tokens.
- Existing gateway admission, outbox, NATS-delivery, and Python-handoff measurements remain distinct.

- [ ] **Step 1: Add failing observability assertions**

  Add `test_bridge_client_logs_task_id_and_duration_without_payload_or_token` and `test_bridge_client_logs_failed_dispatch_duration`. Assert successful and failed logs include task ID and `dispatch_duration_ms`, never include serialized task text or bearer token, and do not relabel `python_handoff_ms` as CCCC acknowledgement latency.

- [ ] **Step 2: Run the focused test and confirm it fails**

  Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cccc_bridge_client.py -q`
  Expected: bridge dispatch timing assertions fail before instrumentation is added.

- [ ] **Step 3: Add Compose configuration and documentation**

  Keep memory as the default. Add environment-based opt-in for `cccc-bridge`; require the token to be supplied at runtime without committing a value. Document the Windows host bridge command, how to select a Docker-reachable host interface, how to constrain inbound firewall access to the local Docker network, and how to stop the bridge/daemon. Explain that CCCC acknowledgement is not model-start latency.

- [ ] **Step 4: Run focused verification**

  Run: `.\.venv\Scripts\python.exe -m pytest tests/test_cccc_bridge_client.py -q`
  Expected: PASS; logs contain only correlation IDs and elapsed milliseconds.

- [ ] **Step 5: Commit the task**

  ```bash
  git add deploy/docker-compose.gateway.yml README.md docs/ARQUITECTURA.md src/trama_platform/cccc_bridge_client.py tests/test_cccc_bridge_client.py
  git commit -m "docs: configure and measure CCCC gateway dispatch"
  ```

### Task 5: Run a real, read-only end-to-end latency probe

**Files:**
- No product files; use the existing local Compose deployment and CCCC installation.

**Interfaces:**
- Submit one task through the Go gateway to the existing `integration-smoke` project using an explicitly approved CCCC actor.
- The probe objective asks the actor only to reply `RECEIVED`; it forbids shell/tool use and repository edits.

- [ ] **Step 1: Verify prerequisites without changing CCCC state**

  Check the configured CCCC executable/version, selected actor allowlist, CCCC daemon status, bridge host binding, and Docker-to-host route. Do not enable a listener on a public interface. If the route requires a broadly exposed listener or privileged firewall change, stop and request a design decision.

- [ ] **Step 2: Start the approved local services and verify health**

  Start the CCCC daemon and bridge only after confirming the selected local configuration; rebuild/recreate only the Python worker using the existing WSL Docker/Compose workflow. Verify bridge health and that TRAMA reports `cccc-bridge` before submitting the probe.

- [ ] **Step 3: Submit one read-only probe through the Go gateway**

  Use a unique task ID, the `integration-smoke` project, an allowlisted actor, empty allowed paths, and acceptance criteria requiring exactly a receipt acknowledgement with no commands or file changes. Do not submit if CCCC cannot guarantee an actor is available for the configured group.

- [ ] **Step 4: Correlate and report measurements**

  Record gateway admission, outbox age, NATS-to-worker, Python handoff, worker-to-bridge, and CCCC acknowledgement timestamps by task ID. Inspect CCCC ledger/runtime output for a verifiable agent-start or first-response event. Report those latter timings only if the event exists; otherwise report gateway-to-CCCC-ack and explicitly mark model latency unavailable. Confirm the repository has no probe-created file changes and stop only the bridge/daemon started for this probe.

- [ ] **Step 5: Review the final smoke evidence**

  Expected: exactly one correlated CCCC tracking record after replaying the same task ID, a clear per-stage timing report, no task body/token in logs, and no repository changes caused by the probe.

## Execution Notes

- Do not run multiple Python workers on the same durable consumer during the probe.
- Before rebuilding the Compose worker, inspect the active project/task state and preserve the user's existing services and data volumes.
- Run Go/container commands in WSL as required by `AGENTS.md`.
- The local system already has unrelated uncommitted changes. Stage and commit only files listed under the task being completed.
