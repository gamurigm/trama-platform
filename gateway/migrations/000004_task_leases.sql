-- Durable ownership for task execution across control-plane replicas.
CREATE TABLE IF NOT EXISTS trama.task_leases (
    organization_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    owner_id TEXT NOT NULL,
    lease_token TEXT NOT NULL,
    attempt INTEGER NOT NULL,
    claimed_at TIMESTAMPTZ NOT NULL,
    expires_at TIMESTAMPTZ NOT NULL,
    completed BOOLEAN NOT NULL DEFAULT FALSE,
    PRIMARY KEY (organization_id, task_id)
);

CREATE INDEX IF NOT EXISTS task_leases_active_idx
    ON trama.task_leases (organization_id, expires_at)
    WHERE completed = FALSE;

INSERT INTO trama.schema_migrations(version) VALUES (4)
ON CONFLICT DO NOTHING;
