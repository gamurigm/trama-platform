package outbox

import (
	"context"
	"fmt"

	"github.com/nats-io/nats.go"
)

// JetStreamClient is the narrow NATS boundary used by the outbox publisher.
type JetStreamClient interface {
	PublishMsg(*nats.Msg, ...nats.PubOpt) (*nats.PubAck, error)
}

// NATSPublisher publishes durable outbox events with JetStream de-duplication.
type NATSPublisher struct {
	client JetStreamClient
}

func NewNATSPublisher(client JetStreamClient) *NATSPublisher {
	return &NATSPublisher{client: client}
}

func (p *NATSPublisher) Publish(ctx context.Context, event Event) error {
	message := nats.NewMsg(event.Subject)
	message.Data = event.Payload
	message.Header.Set("Nats-Msg-Id", event.ID)
	if _, err := p.client.PublishMsg(message, nats.Context(ctx), nats.MsgId(event.ID)); err != nil {
		return fmt.Errorf("publish JetStream event: %w", err)
	}
	return nil
}
