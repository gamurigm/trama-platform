CREATE SCHEMA IF NOT EXISTS gateway;

CREATE TABLE IF NOT EXISTS gateway.admissions (
    admission_id TEXT PRIMARY KEY,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    idempotency_key TEXT NOT NULL,
    request_hash TEXT NOT NULL,
    payload JSONB NOT NULL,
    status TEXT NOT NULL CHECK (status = 'accepted'),
    created_at TIMESTAMPTZ NOT NULL,
    UNIQUE (organization_id, idempotency_key),
    UNIQUE (organization_id, task_id)
);

CREATE TABLE IF NOT EXISTS gateway.task_projection (
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    state TEXT NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL,
    PRIMARY KEY (organization_id, task_id)
);

CREATE INDEX IF NOT EXISTS task_projection_project_updated_idx
    ON gateway.task_projection (organization_id, project_id, updated_at DESC);

CREATE TABLE IF NOT EXISTS gateway.outbox (
    event_id TEXT PRIMARY KEY,
    event_type TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    payload JSONB NOT NULL,
    created_at TIMESTAMPTZ NOT NULL,
    published_at TIMESTAMPTZ,
    attempts INTEGER NOT NULL DEFAULT 0,
    available_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    claim_token TEXT,
    claimed_until TIMESTAMPTZ
);

CREATE INDEX IF NOT EXISTS outbox_ready_idx
    ON gateway.outbox (available_at, created_at)
    WHERE published_at IS NULL;
