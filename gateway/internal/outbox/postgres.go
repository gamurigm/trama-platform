package outbox

import (
	"context"
	"crypto/rand"
	"database/sql"
	"encoding/hex"
	"fmt"
)

type PostgresStore struct {
	db *sql.DB
}

func NewPostgresStore(db *sql.DB) *PostgresStore {
	return &PostgresStore{db: db}
}

func (s *PostgresStore) Claim(ctx context.Context, limit int) ([]Event, error) {
	if limit < 1 {
		return nil, nil
	}
	claimToken := newToken()
	rows, err := s.db.QueryContext(ctx, `
        WITH ready AS (
            SELECT event_id FROM gateway.outbox
            WHERE published_at IS NULL
              AND available_at <= CURRENT_TIMESTAMP
              AND (claimed_until IS NULL OR claimed_until <= CURRENT_TIMESTAMP)
            ORDER BY created_at, event_id
            FOR UPDATE SKIP LOCKED
            LIMIT $1
        )
        UPDATE gateway.outbox AS outbox
        SET claim_token = $2,
            claimed_until = CURRENT_TIMESTAMP + INTERVAL '60 seconds',
            attempts = attempts + 1
        FROM ready
        WHERE outbox.event_id = ready.event_id
		RETURNING outbox.event_id, outbox.event_type, outbox.payload, outbox.task_id, outbox.created_at`, limit, claimToken)
	if err != nil {
		return nil, fmt.Errorf("claim outbox rows: %w", err)
	}
	defer rows.Close()

	var events []Event
	for rows.Next() {
		var event Event
		if err := rows.Scan(&event.ID, &event.Type, &event.Payload, &event.TaskID, &event.CreatedAt); err != nil {
			return nil, fmt.Errorf("scan outbox row: %w", err)
		}
		event.Subject = "trama." + event.Type
		event.ClaimToken = claimToken
		events = append(events, event)
	}
	if err := rows.Err(); err != nil {
		return nil, fmt.Errorf("iterate outbox rows: %w", err)
	}
	return events, nil
}

func (s *PostgresStore) MarkPublished(ctx context.Context, event Event) error {
	result, err := s.db.ExecContext(ctx, `
        UPDATE gateway.outbox
        SET published_at = CURRENT_TIMESTAMP, claim_token = NULL, claimed_until = NULL
        WHERE event_id = $1 AND claim_token = $2 AND published_at IS NULL`, event.ID, event.ClaimToken)
	if err != nil {
		return fmt.Errorf("mark outbox event: %w", err)
	}
	rows, err := result.RowsAffected()
	if err != nil {
		return fmt.Errorf("read mark result: %w", err)
	}
	if rows != 1 {
		return fmt.Errorf("outbox event %s lease expired", event.ID)
	}
	return nil
}

func (s *PostgresStore) Release(ctx context.Context, event Event) error {
	_, err := s.db.ExecContext(ctx, `
        UPDATE gateway.outbox
        SET claim_token = NULL, claimed_until = NULL,
            available_at = CURRENT_TIMESTAMP + INTERVAL '5 seconds'
        WHERE event_id = $1 AND claim_token = $2 AND published_at IS NULL`, event.ID, event.ClaimToken)
	if err != nil {
		return fmt.Errorf("release outbox event: %w", err)
	}
	return nil
}

func newToken() string {
	value := make([]byte, 16)
	if _, err := rand.Read(value); err != nil {
		panic("cannot create outbox claim token: " + err.Error())
	}
	return hex.EncodeToString(value)
}
