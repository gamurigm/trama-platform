# CCCC Host Bridge Design

**Status:** Awaiting user review.

## Goal

Measure and enable the real dispatch path from the Go gateway through the
Python worker to a CCCC actor on the Windows host. Preserve the current
PostgreSQL outbox and NATS JetStream admission path.

## User intent and current state

The user wants to know whether the task can reach the real agent/model faster,
and where the time is spent. The existing instrumented smoke measured about
264 ms from gateway admission through Python handoff. That measurement did not
include CCCC or model execution: the Docker worker uses `InMemoryCoordination`,
and the CCCC executable is installed on Windows, not in the Linux container.

The API process can construct `CcccCliAdapter`, but `serve_task_worker` builds
`TramaRuntime` without a coordination adapter. The Python worker and control
plane share a SQLite state volume. The CCCC CLI supports `tracked-send` and an
idempotency key. The CCCC daemon is currently stopped.

## Recommended architecture

Keep the gateway, PostgreSQL, outbox, NATS, Python worker, and shared SQLite
state in Docker. Add a narrowly scoped host bridge on Windows. The worker calls
the bridge over a private Docker-to-host route; the bridge invokes the installed
CCCC CLI with a fixed command shape. No arbitrary executable, shell string, or
CLI arguments come from the task payload.

The bridge exposes two authenticated operations: submit a task to CCCC and
forward an `AgentResult` to the configured result recipient. Task submissions
carry the validated task envelope and task ID. The bridge uses the task ID as
the CCCC idempotency key and invokes the existing `tracked-send` operation.
Task recipients and the result recipient are configured or allowlisted locally;
the bridge never accepts arbitrary CLI arguments from a request. It returns
the CCCC tracking identifier when available.

The Python worker constructs a bridge-backed `CoordinationPort` when that
backend is selected. The default remains in-memory for local development. The
control-plane API and worker must report the selected backend so an operator
can tell which path is active.

## Data flow and measurements

1. The Go gateway admits the task and commits it to PostgreSQL.
2. The outbox publishes the task to JetStream.
3. The Python consumer validates, deduplicates, persists, and queues the task.
4. The dispatcher posts the task to the Windows bridge.
5. The bridge runs `cccc tracked-send`; successful return means CCCC accepted
   the handoff, not that an agent started model inference.
6. If available, CCCC ledger/runtime timestamps are correlated by task ID to
   measure agent start or first response separately.
7. When TRAMA receives an `AgentResult`, its coordination adapter forwards it
   through the bridge to the configured CCCC result recipient using the
   existing `send` operation.

Emit structured timing for bridge request duration and CCCC acknowledgement,
with task ID and tracking ID. Continue to use the existing admission, outbox,
and NATS timestamps. Do not log task bodies, credentials, or model output.
Report first-agent-response latency only if CCCC provides a verifiable event or
timestamp; otherwise report gateway-to-CCCC-ack and state that the model timing
is unavailable.

## Reliability and security

- Authenticate worker-to-bridge requests with a locally configured bearer
  secret; do not commit it or place it in task payloads.
- Bind the bridge only to an interface reachable by the local Docker network,
  restrict inbound access to that network, and expose no public endpoint.
- Construct CCCC invocations as argument arrays, never through a shell.
- Use the task ID for idempotency so JetStream redelivery does not create a
  second CCCC task.
- Fix the result recipient in local bridge configuration; do not let an
  `AgentResult` choose an arbitrary CCCC recipient.
- Validate task and result payloads before invoking CCCC, and return a failed
  dispatch when CCCC rejects or times out.
- A bridge failure must be visible as a failed dispatch in TRAMA and retain the
  existing retry path. It must not be reported as a successful CCCC handoff.
- A read-only latency probe must contain explicit no-file-change and no-command
  constraints and use an approved actor.

## Scope and non-goals

This change is for a local end-to-end latency probe and a usable local CCCC
dispatch path. It does not replace PostgreSQL, NATS, or SQLite; run CCCC inside
Docker; alter task admission semantics; or claim that CCCC acknowledgement is
the first model token. It does not add Redis to the task dispatch path.

## Acceptance criteria

- The worker reports the configured CCCC bridge backend rather than silently
  using in-memory coordination.
- Both `CoordinationPort.submit_task` and `CoordinationPort.record_result`
  work through the bridge and preserve the configured task and result
  recipients.
- A safe task submitted through the Go gateway is correlated through gateway,
  outbox, NATS, Python worker, bridge, and CCCC tracking ID.
- The timing report separates gateway-to-Python handoff from Python-to-CCCC
  acknowledgement and does not double-count overlapping intervals.
- Re-delivery with the same task ID does not create a duplicate CCCC task.
- Bridge authentication failure, timeout, or CCCC unavailability is visible
  as a failed dispatch and does not produce a false success measurement.
- Any model-start or first-response timing is backed by an actual CCCC event;
  otherwise the report clearly stops at CCCC acknowledgement.
- The smoke task performs no repository edits and runs no commands.

## Open implementation detail

Confirm how CCCC reports task start and first response (ledger or runtime event)
before promising model latency. Also confirm the narrowest Windows listener
binding and Docker-network access pattern supported on this host. These checks
belong in the implementation plan and probe setup; they do not change the
bridge boundary described here.
