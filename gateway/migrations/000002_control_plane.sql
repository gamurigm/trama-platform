-- TRAMA control plane. PostgreSQL is the shared source of truth in production.
CREATE SCHEMA IF NOT EXISTS trama;

CREATE TABLE IF NOT EXISTS trama.schema_migrations (
    version INTEGER PRIMARY KEY,
    applied_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trama.projects (
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    repository TEXT NOT NULL,
    default_branch TEXT NOT NULL,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (organization_id, project_id)
);

CREATE TABLE IF NOT EXISTS trama.requirements (
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (organization_id, requirement_id),
    FOREIGN KEY (organization_id, project_id)
        REFERENCES trama.projects (organization_id, project_id)
);

CREATE TABLE IF NOT EXISTS trama.plans (
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    proposal_id TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (organization_id, proposal_id),
    FOREIGN KEY (organization_id, project_id)
        REFERENCES trama.projects (organization_id, project_id)
);

CREATE TABLE IF NOT EXISTS trama.phases (
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    phase_id TEXT NOT NULL,
    requirement_id TEXT NOT NULL,
    status TEXT NOT NULL,
    sequence INTEGER NOT NULL,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (organization_id, phase_id),
    FOREIGN KEY (organization_id, project_id)
        REFERENCES trama.projects (organization_id, project_id)
);

CREATE TABLE IF NOT EXISTS trama.tasks (
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    requirement_id TEXT,
    phase_id TEXT,
    state TEXT NOT NULL,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (organization_id, task_id),
    FOREIGN KEY (organization_id, project_id)
        REFERENCES trama.projects (organization_id, project_id)
);

CREATE TABLE IF NOT EXISTS trama.results (
    task_id TEXT PRIMARY KEY,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS trama.memory_candidates (
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    candidate_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (organization_id, candidate_id),
    FOREIGN KEY (organization_id, project_id)
        REFERENCES trama.projects (organization_id, project_id)
);

CREATE TABLE IF NOT EXISTS trama.promotions (
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    promotion_id TEXT NOT NULL,
    status TEXT NOT NULL,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (organization_id, promotion_id),
    FOREIGN KEY (organization_id, project_id)
        REFERENCES trama.projects (organization_id, project_id)
);

-- Generic records preserve v1 payload compatibility while typed tables are
-- introduced incrementally and provide relational namespace indexes.
CREATE TABLE IF NOT EXISTS trama.state_records (
    kind TEXT NOT NULL,
    record_id TEXT NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT,
    payload JSONB NOT NULL,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (kind, organization_id, record_id)
);

CREATE INDEX IF NOT EXISTS state_records_namespace_idx
    ON trama.state_records (organization_id, project_id, kind);

CREATE TABLE IF NOT EXISTS trama.operation_events (
    event_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT,
    requirement_id TEXT,
    phase_id TEXT,
    task_id TEXT,
    correlation_id TEXT,
    action TEXT NOT NULL,
    status TEXT NOT NULL,
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS operation_events_namespace_idx
    ON trama.operation_events (organization_id, project_id, created_at, event_id);

CREATE TABLE IF NOT EXISTS trama.task_logs (
    log_id TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL,
    organization_id TEXT NOT NULL,
    project_id TEXT NOT NULL,
    requirement_id TEXT,
    phase_id TEXT,
    task_id TEXT,
    level TEXT NOT NULL,
    sequence BIGINT NOT NULL,
    payload JSONB NOT NULL
);

CREATE INDEX IF NOT EXISTS task_logs_project_idx
    ON trama.task_logs (organization_id, project_id, created_at, sequence, log_id);

CREATE INDEX IF NOT EXISTS task_logs_task_idx
    ON trama.task_logs (organization_id, project_id, task_id, created_at, sequence);

CREATE TABLE IF NOT EXISTS trama.consumed_events (
    event_id TEXT PRIMARY KEY,
    claimed_until TIMESTAMPTZ NOT NULL,
    completed BOOLEAN NOT NULL DEFAULT FALSE
);

INSERT INTO trama.schema_migrations(version) VALUES (2)
ON CONFLICT DO NOTHING;
