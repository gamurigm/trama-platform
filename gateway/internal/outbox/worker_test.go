package outbox

import (
	"context"
	"encoding/json"
	"testing"
)

func TestWorkerPublishesEachPendingEventOnceAndMarksItPublished(t *testing.T) {
	store := NewMemoryStore([]Event{{
		ID:      "event-1",
		Type:    "task.admitted.v1",
		Subject: "trama.task.admitted.v1",
		Payload: json.RawMessage(`{"task_id":"task-1"}`),
	}})
	publisher := &MemoryPublisher{}
	worker := NewWorker(store, publisher)

	published, err := worker.PublishPending(context.Background(), 10)
	if err != nil {
		t.Fatalf("publish pending events: %v", err)
	}
	if published != 1 {
		t.Fatalf("expected one published event, got %d", published)
	}
	if got := publisher.Messages(); len(got) != 1 || got[0].Subject != "trama.task.admitted.v1" {
		t.Fatalf("expected one task subject publication, got %#v", got)
	}

	published, err = worker.PublishPending(context.Background(), 10)
	if err != nil {
		t.Fatalf("republish pending events: %v", err)
	}
	if published != 0 {
		t.Fatalf("expected no republished events, got %d", published)
	}
}
