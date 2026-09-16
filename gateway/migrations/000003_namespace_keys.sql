-- Upgrade generic control-plane records so identifiers are tenant-scoped.
DO $$
BEGIN
    IF EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = to_regclass('trama.state_records')
          AND conname = 'state_records_pkey'
    ) THEN
        ALTER TABLE trama.state_records DROP CONSTRAINT state_records_pkey;
    END IF;

    IF NOT EXISTS (
        SELECT 1
        FROM pg_constraint
        WHERE conrelid = to_regclass('trama.state_records')
          AND conname = 'state_records_namespace_pkey'
    ) THEN
        ALTER TABLE trama.state_records
            ADD CONSTRAINT state_records_namespace_pkey
            PRIMARY KEY (kind, organization_id, record_id);
    END IF;
END $$;

INSERT INTO trama.schema_migrations(version) VALUES (3)
ON CONFLICT DO NOTHING;
