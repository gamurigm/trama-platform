// Package outbox publishes durable events after their database transaction commits.
package outbox

import (
	"context"
	"encoding/json"
	"fmt"
	"log/slog"
	"sync"
	"time"
)

type Event struct {
	ID         string
	Type       string
	TaskID     string
	CreatedAt  time.Time
	Subject    string
	Payload    json.RawMessage
	ClaimToken string
}

type Store interface {
	Claim(context.Context, int) ([]Event, error)
	MarkPublished(context.Context, Event) error
	Release(context.Context, Event) error
}

type Publisher interface {
	Publish(context.Context, Event) error
}

type Worker struct {
	store     Store
	publisher Publisher
}

func NewWorker(store Store, publisher Publisher) *Worker {
	return &Worker{store: store, publisher: publisher}
}

func (w *Worker) PublishPending(ctx context.Context, limit int) (int, error) {
	events, err := w.store.Claim(ctx, limit)
	if err != nil {
		return 0, fmt.Errorf("claim outbox events: %w", err)
	}
	published := 0
	for _, event := range events {
		if err := w.publisher.Publish(ctx, event); err != nil {
			_ = w.store.Release(ctx, event)
			return published, fmt.Errorf("publish %s: %w", event.ID, err)
		}
		if err := w.store.MarkPublished(ctx, event); err != nil {
			return published, fmt.Errorf("mark %s published: %w", event.ID, err)
		}
		if event.CreatedAt.IsZero() {
			slog.Info("gateway outbox event published", "event_id", event.ID, "task_id", event.TaskID)
		} else {
			slog.Info("gateway outbox event published",
				"event_id", event.ID,
				"task_id", event.TaskID,
				"outbox_age_ms", time.Since(event.CreatedAt).Milliseconds(),
			)
		}
		published++
	}
	return published, nil
}

// MemoryStore supports deterministic unit tests and local development.
type MemoryStore struct {
	mu     sync.Mutex
	events map[string]memoryEvent
}

type memoryEvent struct {
	event     Event
	claimed   bool
	published bool
}

func NewMemoryStore(events []Event) *MemoryStore {
	stored := make(map[string]memoryEvent, len(events))
	for _, event := range events {
		stored[event.ID] = memoryEvent{event: event}
	}
	return &MemoryStore{events: stored}
}

func (s *MemoryStore) Claim(_ context.Context, limit int) ([]Event, error) {
	if limit < 1 {
		return nil, nil
	}
	s.mu.Lock()
	defer s.mu.Unlock()
	claimed := make([]Event, 0, limit)
	for id, entry := range s.events {
		if entry.claimed || entry.published {
			continue
		}
		entry.claimed = true
		s.events[id] = entry
		claimed = append(claimed, entry.event)
		if len(claimed) == limit {
			break
		}
	}
	return claimed, nil
}

func (s *MemoryStore) MarkPublished(_ context.Context, event Event) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	entry, ok := s.events[event.ID]
	if !ok {
		return fmt.Errorf("unknown outbox event %s", event.ID)
	}
	entry.claimed = false
	entry.published = true
	s.events[event.ID] = entry
	return nil
}

func (s *MemoryStore) Release(_ context.Context, event Event) error {
	s.mu.Lock()
	defer s.mu.Unlock()
	entry, ok := s.events[event.ID]
	if !ok {
		return fmt.Errorf("unknown outbox event %s", event.ID)
	}
	entry.claimed = false
	s.events[event.ID] = entry
	return nil
}

type Message struct {
	EventID string
	Subject string
	Payload []byte
}

type MemoryPublisher struct {
	mu       sync.Mutex
	messages []Message
}

func (p *MemoryPublisher) Publish(_ context.Context, event Event) error {
	p.mu.Lock()
	defer p.mu.Unlock()
	p.messages = append(p.messages, Message{
		EventID: event.ID,
		Subject: event.Subject,
		Payload: append([]byte(nil), event.Payload...),
	})
	return nil
}

func (p *MemoryPublisher) Messages() []Message {
	p.mu.Lock()
	defer p.mu.Unlock()
	return append([]Message(nil), p.messages...)
}
