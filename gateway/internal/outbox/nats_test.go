package outbox

import (
	"context"
	"encoding/json"
	"testing"

	"github.com/nats-io/nats.go"
)

func TestNATSPublisherSetsTheOutboxEventAsTheJetStreamMessageID(t *testing.T) {
	client := &recordingJetStream{}
	publisher := NewNATSPublisher(client)
	event := Event{
		ID:      "event-1",
		Subject: "trama.task.admitted.v1",
		Payload: json.RawMessage(`{"task_id":"task-1"}`),
	}

	if err := publisher.Publish(context.Background(), event); err != nil {
		t.Fatalf("publish event: %v", err)
	}

	if client.message == nil {
		t.Fatal("expected one JetStream message")
	}
	if got := client.message.Header.Get("Nats-Msg-Id"); got != "event-1" {
		t.Fatalf("expected Nats-Msg-Id event-1, got %q", got)
	}
	if got := client.message.Subject; got != "trama.task.admitted.v1" {
		t.Fatalf("expected task subject, got %q", got)
	}
}

type recordingJetStream struct {
	message *nats.Msg
}

func (c *recordingJetStream) PublishMsg(message *nats.Msg, _ ...nats.PubOpt) (*nats.PubAck, error) {
	c.message = message
	return &nats.PubAck{}, nil
}
