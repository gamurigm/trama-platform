// Package admission owns the durable boundary where task requests enter TRAMA.
package admission

import (
	"context"
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"errors"
	"sync"
	"time"
)

// Task is the gateway representation of the public task-envelope v1 contract.
// Python remains the owner of state transitions after admission.
type Task struct {
	SchemaVersion  string    `json:"schema_version"`
	TaskID         string    `json:"task_id"`
	ParentTaskID   *string   `json:"parent_task_id,omitempty"`
	RequirementID  *string   `json:"requirement_id,omitempty"`
	PhaseID        *string   `json:"phase_id,omitempty"`
	Source         string    `json:"source"`
	DependsOn      []string  `json:"depends_on,omitempty"`
	ApprovedBy     *string   `json:"approved_by,omitempty"`
	OrganizationID string    `json:"organization_id"`
	ProjectID      string    `json:"project_id"`
	Repository     string    `json:"repository"`
	Objective      string    `json:"objective"`
	Actor          string    `json:"actor"`
	Branch         string    `json:"branch"`
	Worktree       string    `json:"worktree"`
	AllowedPaths   []string  `json:"allowed_paths,omitempty"`
	ReadOnly       bool      `json:"read_only"`
	State          string    `json:"state"`
	Criteria       []string  `json:"acceptance_criteria"`
	CreatedAt      time.Time `json:"created_at"`
}

// Admission is the read-your-write record returned to an HTTP client.
type Admission struct {
	AdmissionID string `json:"admission_id"`
	TaskID      string `json:"task_id"`
	Status      string `json:"status"`
}

// OutboxEvent is published asynchronously after the admission transaction commits.
type OutboxEvent struct {
	ID        string    `json:"event_id"`
	Type      string    `json:"type"`
	Task      Task      `json:"task"`
	Payload   []byte    `json:"payload"`
	CreatedAt time.Time `json:"created_at"`
}

var ErrInvalidTask = errors.New("task is missing required fields")
var ErrMissingIdempotencyKey = errors.New("idempotency key is required")
var ErrIdempotencyConflict = errors.New("idempotency key was reused with a different task")
var ErrTaskConflict = errors.New("task id was reused with a different task")
var ErrTaskNotFound = errors.New("task was not found")

// Store persists an admission, idempotency key and outbox event atomically.
type Store interface {
	Admit(context.Context, Task, string, string, func() string, time.Time) (Admission, error)
}

type TaskReader interface {
	GetTask(context.Context, string, string) (Task, error)
}

// Service applies gateway-level admission rules without taking ownership of execution.
type Service struct {
	store Store
	now   func() time.Time
	newID func() string
}

func NewService(store Store) *Service {
	return &Service{
		store: store,
		now:   func() time.Time { return time.Now().UTC() },
		newID: newID,
	}
}

func (s *Service) Admit(ctx context.Context, task Task, idempotencyKey string) (Admission, error) {
	if task.TaskID == "" || task.OrganizationID == "" || task.ProjectID == "" || task.Repository == "" ||
		task.Objective == "" || task.Actor == "" || task.Branch == "" || task.Worktree == "" || len(task.Criteria) == 0 {
		return Admission{}, ErrInvalidTask
	}
	if task.Source != "" && task.Source != "manual" && task.Source != "requirement" {
		return Admission{}, ErrInvalidTask
	}
	if task.Source == "requirement" && (task.RequirementID == nil || task.PhaseID == nil) {
		return Admission{}, ErrInvalidTask
	}
	if task.State != "" && task.State != "accepted" && task.State != "planned" {
		return Admission{}, ErrInvalidTask
	}
	if idempotencyKey == "" {
		return Admission{}, ErrMissingIdempotencyKey
	}
	requestFingerprint := fingerprint(task)
	now := s.now()
	task = normalizeTask(task, now)
	return s.store.Admit(ctx, task, idempotencyKey, requestFingerprint, s.newID, now)
}

// MemoryStore is a concurrency-safe development/test adapter. Production uses PostgresStore.
type MemoryStore struct {
	mu           sync.Mutex
	admissions   map[string]storedAdmission
	tasks        map[string]storedAdmission
	taskPayloads map[string]Task
	outboxEvents []OutboxEvent
}

func NewMemoryStore() *MemoryStore {
	return &MemoryStore{
		admissions:   make(map[string]storedAdmission),
		tasks:        make(map[string]storedAdmission),
		taskPayloads: make(map[string]Task),
	}
}

type storedAdmission struct {
	admission   Admission
	fingerprint string
}

func (s *MemoryStore) Admit(_ context.Context, task Task, key, requestFingerprint string, newID func() string, now time.Time) (Admission, error) {
	s.mu.Lock()
	defer s.mu.Unlock()

	if existing, ok := s.admissions[key]; ok {
		if existing.fingerprint != requestFingerprint {
			return Admission{}, ErrIdempotencyConflict
		}
		return existing.admission, nil
	}
	taskIdentity := task.OrganizationID + "\x00" + task.TaskID
	if existing, ok := s.tasks[taskIdentity]; ok {
		if existing.fingerprint != requestFingerprint {
			return Admission{}, ErrTaskConflict
		}
		s.admissions[key] = existing
		return existing.admission, nil
	}
	admission := Admission{AdmissionID: newID(), TaskID: task.TaskID, Status: "accepted"}
	eventID := newID()
	s.admissions[key] = storedAdmission{admission: admission, fingerprint: requestFingerprint}
	s.tasks[taskIdentity] = storedAdmission{admission: admission, fingerprint: requestFingerprint}
	s.taskPayloads[taskIdentity] = task
	s.outboxEvents = append(s.outboxEvents, OutboxEvent{
		ID:        eventID,
		Type:      "task.admitted.v1",
		Task:      task,
		Payload:   eventPayload(eventID, task),
		CreatedAt: now,
	})
	return admission, nil
}

func (s *MemoryStore) GetTask(_ context.Context, organizationID, taskID string) (Task, error) {
	s.mu.Lock()
	defer s.mu.Unlock()
	task, ok := s.taskPayloads[organizationID+"\x00"+taskID]
	if !ok {
		return Task{}, ErrTaskNotFound
	}
	return task, nil
}

func (s *MemoryStore) Outbox() []OutboxEvent {
	s.mu.Lock()
	defer s.mu.Unlock()
	return append([]OutboxEvent(nil), s.outboxEvents...)
}

func fingerprint(task Task) string {
	payload, err := json.Marshal(task)
	if err != nil {
		panic("cannot encode task payload: " + err.Error())
	}
	digest := sha256.Sum256(payload)
	return hex.EncodeToString(digest[:])
}

func normalizeTask(task Task, now time.Time) Task {
	if task.SchemaVersion == "" {
		task.SchemaVersion = "1.0"
	}
	if task.State == "" {
		task.State = "accepted"
	}
	if task.Source == "" {
		task.Source = "manual"
	}
	if task.CreatedAt.IsZero() {
		task.CreatedAt = now
	}
	return task
}

func eventPayload(eventID string, task Task) []byte {
	payload, err := json.Marshal(struct {
		SchemaVersion string `json:"schema_version"`
		EventID       string `json:"event_id"`
		EventType     string `json:"event_type"`
		Task          Task   `json:"task"`
	}{
		SchemaVersion: "1.0",
		EventID:       eventID,
		EventType:     "task.admitted.v1",
		Task:          task,
	})
	if err != nil {
		panic("cannot encode task event: " + err.Error())
	}
	return payload
}

func newID() string {
	bytes := make([]byte, 16)
	if _, err := rand.Read(bytes); err != nil {
		panic("cannot create gateway identifier: " + err.Error())
	}
	return hex.EncodeToString(bytes)
}
