package admission

import (
	"context"
	"encoding/json"
	"errors"
	"sync"
	"testing"
)

func TestAdmitTaskStoresOneDurableOutboxEventForAnIdempotentRequest(t *testing.T) {
	store := NewMemoryStore()
	service := NewService(store)
	task := Task{
		TaskID:         "task-1",
		OrganizationID: "org-a",
		ProjectID:      "demo",
		Repository:     "https://example.test/demo",
		Objective:      "Run tests",
		Actor:          "hermes",
		Branch:         "main",
		Worktree:       "C:/work/demo",
		Criteria:       []string{"tests pass"},
	}

	first, err := service.Admit(context.Background(), task, "request-1")
	if err != nil {
		t.Fatalf("admit first request: %v", err)
	}
	second, err := service.Admit(context.Background(), task, "request-1")
	if err != nil {
		t.Fatalf("admit idempotent request: %v", err)
	}

	if first.AdmissionID != second.AdmissionID {
		t.Fatalf("expected the idempotent request to reuse admission %q, got %q", first.AdmissionID, second.AdmissionID)
	}
	if first.Status != "accepted" {
		t.Fatalf("expected accepted status, got %q", first.Status)
	}
	if got := len(store.Outbox()); got != 1 {
		t.Fatalf("expected one durable outbox event, got %d", got)
	}
	if got := store.Outbox()[0].Type; got != "task.admitted.v1" {
		t.Fatalf("expected task.admitted.v1 event, got %q", got)
	}
	var envelope struct {
		EventID   string `json:"event_id"`
		EventType string `json:"event_type"`
		Task      Task   `json:"task"`
	}
	if err := json.Unmarshal(store.Outbox()[0].Payload, &envelope); err != nil {
		t.Fatalf("decode outbox envelope: %v", err)
	}
	if envelope.EventID == "" || envelope.EventType != "task.admitted.v1" {
		t.Fatalf("unexpected outbox envelope: %#v", envelope)
	}
	if envelope.Task.TaskID != task.TaskID || envelope.Task.State != "accepted" {
		t.Fatalf("unexpected outbox task: %#v", envelope.Task)
	}
}

func TestAdmitTaskRejectsAReusedIdempotencyKeyWithDifferentPayload(t *testing.T) {
	store := NewMemoryStore()
	service := NewService(store)
	task := Task{
		TaskID:         "task-1",
		OrganizationID: "org-a",
		ProjectID:      "demo",
		Repository:     "https://example.test/demo",
		Objective:      "Run tests",
		Actor:          "hermes",
		Branch:         "main",
		Worktree:       "C:/work/demo",
		Criteria:       []string{"tests pass"},
	}
	if _, err := service.Admit(context.Background(), task, "request-1"); err != nil {
		t.Fatalf("admit first request: %v", err)
	}

	changedTask := task
	changedTask.Objective = "Deploy the project"
	_, err := service.Admit(context.Background(), changedTask, "request-1")

	if !errors.Is(err, ErrIdempotencyConflict) {
		t.Fatalf("expected idempotency conflict, got %v", err)
	}
	if got := len(store.Outbox()); got != 1 {
		t.Fatalf("expected one durable outbox event, got %d", got)
	}
}

func TestAdmitTaskIsIdempotentByOrganizationAndTaskIDAcrossKeys(t *testing.T) {
	store := NewMemoryStore()
	service := NewService(store)
	task := Task{
		TaskID:         "task-1",
		OrganizationID: "org-a",
		ProjectID:      "demo",
		Repository:     "https://example.test/demo",
		Objective:      "Run tests",
		Actor:          "hermes",
		Branch:         "main",
		Worktree:       "C:/work/demo",
		Criteria:       []string{"tests pass"},
	}
	first, err := service.Admit(context.Background(), task, "request-1")
	if err != nil {
		t.Fatalf("admit first task: %v", err)
	}
	second, err := service.Admit(context.Background(), task, "request-2")
	if err != nil {
		t.Fatalf("admit same task with another delivery key: %v", err)
	}
	if first != second || len(store.Outbox()) != 1 {
		t.Fatalf("expected one task admission, got %#v, %#v and %d events", first, second, len(store.Outbox()))
	}

	changed := task
	changed.Objective = "Deploy"
	if _, err := service.Admit(context.Background(), changed, "request-3"); !errors.Is(err, ErrTaskConflict) {
		t.Fatalf("expected task conflict, got %v", err)
	}
}

func TestMemoryAdmissionSerializesAConcurrentIdempotentBurst(t *testing.T) {
	store := NewMemoryStore()
	service := NewService(store)
	task := Task{
		TaskID:         "burst-task",
		OrganizationID: "org-a",
		ProjectID:      "demo",
		Repository:     "repo",
		Objective:      "Run tests",
		Actor:          "hermes",
		Branch:         "main",
		Worktree:       "C:/work/demo",
		Criteria:       []string{"tests pass"},
	}
	const requests = 128
	admissions := make([]Admission, requests)
	errorsSeen := make([]error, requests)
	var group sync.WaitGroup
	for index := 0; index < requests; index++ {
		group.Add(1)
		go func(position int) {
			defer group.Done()
			admissions[position], errorsSeen[position] = service.Admit(
				context.Background(), task, "burst-key",
			)
		}(index)
	}
	group.Wait()

	for index, err := range errorsSeen {
		if err != nil {
			t.Fatalf("concurrent request %d failed: %v", index, err)
		}
		if admissions[index].AdmissionID != admissions[0].AdmissionID {
			t.Fatalf("request %d did not reuse admission %q", index, admissions[0].AdmissionID)
		}
	}
	if got := len(store.Outbox()); got != 1 {
		t.Fatalf("expected one outbox event for burst, got %d", got)
	}
}
