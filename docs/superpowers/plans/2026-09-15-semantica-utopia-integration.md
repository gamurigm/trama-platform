# Semantica and Utopia Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace TRAMA's incompatible memory/knowledge HTTP assumptions with adapters matching the real Semantica Python/MCP and Utopia MCP usage models.

**Architecture:** Semantica is used through an injected Python `AgentContext`-compatible object, with TRAMA metadata and local candidate indexing. Utopia is used through an injected MCP tool caller, with configurable tool names and base/scope arguments. Existing ports remain stable and local implementations remain the fallback.

**Tech Stack:** Python 3.12, Pydantic, pytest, HTTPX only for legacy compatibility, MCP-compatible callables.

**Spec:** `docs/superpowers/specs/2026-09-15-semantica-utopia-integration-design.md`

## Global Constraints

- Preserve organization/project isolation and add agent/task provenance.
- Do not expose credentials or secrets in contracts, logs, or docs.
- Do not make external Semantica or Utopia services mandatory for local tests.
- Require approved, conflict-free, validated candidates before Utopia publication.

### Task 1: Provenance-aware memory contracts

**Files:** `src/trama_platform/contracts.py`, `src/trama_platform/namespaces.py`, `tests/test_contracts.py`

- [ ] Write failing tests for `MemoryCandidate.agent_id`, `task_id`, `source`, and context namespace generation.
- [ ] Run `pytest tests/test_contracts.py -q` and confirm the new assertions fail.
- [ ] Add optional bounded provenance fields and a namespace helper that includes organization, project, and agent.
- [ ] Run the focused tests and then the existing contract tests.

### Task 2: Semantica native context adapter

**Files:** `src/trama_platform/semantica_adapter.py`, `tests/test_semantica_adapter.py`, `src/trama_platform/cli.py`, `pyproject.toml`

- [x] Write failing tests for storing metadata-rich facts, scoped retrieval, and candidate lookup.
- [x] Run the focused tests and confirm the adapter is missing.
- [x] Implement an injected `AgentContext` adapter using `store` and `retrieve`, with no hard dependency at import time.
- [x] Wire it behind `TRAMA_SEMANTICA_KG_PATH` and retain local fallback.
- [x] Run focused tests.

### Task 3: Utopia MCP adapter

**Files:** `src/trama_platform/utopia_mcp.py`, `tests/test_utopia_mcp.py`, `src/trama_platform/settings.py`, `src/trama_platform/cli.py`

- [x] Write failing tests for configurable MCP tool calls, approval payloads, scoped search, and error translation.
- [x] Run focused tests and confirm the adapter is missing.
- [x] Implement a synchronous callable-based MCP bridge so TRAMA does not depend on a particular MCP client event loop.
- [x] Add configuration for base URL, knowledge-base ID, and PAT.
- [x] Run focused tests.

### Task 4: Runtime/API integration and documentation

**Files:** `src/trama_platform/runtime.py`, `src/trama_platform/api.py`, `README.md`, `docs/ARQUITECTURA.md`, `.env.example`, tests

- [x] Add failing integration tests proving agent/task provenance and Utopia publication only after validation.
- [x] Wire the adapters without changing the public TRAMA ports.
- [x] Update setup instructions for the two upstream repositories and remove claims about unsupported endpoints.
- [x] Run the full Python suite and record unrelated baseline failures separately.
