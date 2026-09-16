package admission

import (
	"context"
	"database/sql"
	"encoding/json"
	"errors"
	"fmt"
	"time"
)

// PostgresStore is the production Store adapter. It keeps admission,
// read-your-write projection and outbox publication intent in one transaction.
type PostgresStore struct {
	db *sql.DB
}

func NewPostgresStore(db *sql.DB) *PostgresStore {
	return &PostgresStore{db: db}
}

func (s *PostgresStore) GetTask(ctx context.Context, organizationID, taskID string) (Task, error) {
	var payload []byte
	err := s.db.QueryRowContext(ctx, `SELECT payload
		FROM gateway.task_projection
		WHERE organization_id = $1 AND task_id = $2`, organizationID, taskID).Scan(&payload)
	if errors.Is(err, sql.ErrNoRows) {
		return Task{}, ErrTaskNotFound
	}
	if err != nil {
		return Task{}, fmt.Errorf("load task projection: %w", err)
	}
	var task Task
	if err := json.Unmarshal(payload, &task); err != nil {
		return Task{}, fmt.Errorf("decode task projection: %w", err)
	}
	return task, nil
}

func (s *PostgresStore) Admit(
	ctx context.Context,
	task Task,
	key string,
	requestFingerprint string,
	newID func() string,
	now time.Time,
) (Admission, error) {
	payload, err := json.Marshal(task)
	if err != nil {
		return Admission{}, fmt.Errorf("encode task payload: %w", err)
	}
	tx, err := s.db.BeginTx(ctx, nil)
	if err != nil {
		return Admission{}, fmt.Errorf("begin admission transaction: %w", err)
	}
	defer tx.Rollback()

	admission := Admission{AdmissionID: newID(), TaskID: task.TaskID, Status: "accepted"}
	result, err := tx.ExecContext(ctx, `INSERT INTO gateway.admissions
        (admission_id, organization_id, project_id, task_id, idempotency_key, request_hash, payload, status, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
        ON CONFLICT (organization_id, idempotency_key) DO NOTHING`,
		admission.AdmissionID, task.OrganizationID, task.ProjectID, task.TaskID, key,
		requestFingerprint, payload, admission.Status, now)
	if err != nil {
		return Admission{}, fmt.Errorf("insert admission: %w", err)
	}
	inserted, err := result.RowsAffected()
	if err != nil {
		return Admission{}, fmt.Errorf("read admission result: %w", err)
	}
	if inserted == 0 {
		var existingHash string
		if err := tx.QueryRowContext(ctx, `SELECT request_hash, admission_id, task_id, status
            FROM gateway.admissions
            WHERE organization_id = $1 AND idempotency_key = $2`, task.OrganizationID, key).
			Scan(&existingHash, &admission.AdmissionID, &admission.TaskID, &admission.Status); err != nil {
			return Admission{}, fmt.Errorf("load existing admission: %w", err)
		}
		if existingHash != requestFingerprint {
			return Admission{}, ErrIdempotencyConflict
		}
		if err := tx.Commit(); err != nil {
			return Admission{}, fmt.Errorf("commit idempotent admission: %w", err)
		}
		return admission, nil
	}

	projectionResult, err := tx.ExecContext(ctx, `INSERT INTO gateway.task_projection
        (organization_id, project_id, task_id, payload, state, updated_at)
		VALUES ($1, $2, $3, $4, $5, $6)
		ON CONFLICT (organization_id, task_id) DO NOTHING`,
		task.OrganizationID, task.ProjectID, task.TaskID, payload, admission.Status, now)
	if err != nil {
		return Admission{}, fmt.Errorf("insert task projection: %w", err)
	}
	projectionInserted, err := projectionResult.RowsAffected()
	if err != nil {
		return Admission{}, fmt.Errorf("read task projection result: %w", err)
	}
	if projectionInserted == 0 {
		var existingHash string
		var existingAdmissionID string
		var existingStatus string
		if err := tx.QueryRowContext(ctx, `SELECT request_hash, admission_id, status
			FROM gateway.admissions
			WHERE organization_id = $1 AND task_id = $2 AND idempotency_key <> $3
			ORDER BY created_at ASC LIMIT 1`, task.OrganizationID, task.TaskID, key).
			Scan(&existingHash, &existingAdmissionID, &existingStatus); err != nil {
			return Admission{}, fmt.Errorf("load existing task admission: %w", err)
		}
		if existingHash != requestFingerprint {
			return Admission{}, ErrTaskConflict
		}
		return Admission{AdmissionID: existingAdmissionID, TaskID: task.TaskID, Status: existingStatus}, nil
	}
	eventID := newID()
	eventPayload := eventPayload(eventID, task)
	if _, err := tx.ExecContext(ctx, `INSERT INTO gateway.outbox
        (event_id, event_type, organization_id, project_id, task_id, payload, created_at)
        VALUES ($1, $2, $3, $4, $5, $6, $7)`,
		eventID, "task.admitted.v1", task.OrganizationID, task.ProjectID, task.TaskID, eventPayload, now); err != nil {
		return Admission{}, fmt.Errorf("insert outbox event: %w", err)
	}
	if err := tx.Commit(); err != nil {
		return Admission{}, fmt.Errorf("commit admission: %w", err)
	}
	return admission, nil
}
