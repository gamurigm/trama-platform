package main

import (
	"context"
	"database/sql"
	"errors"
	"fmt"
	"log"
	"os"
	"os/signal"
	"strconv"
	"syscall"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
	"github.com/nats-io/nats.go"

	"github.com/gamur/trama/gateway/internal/outbox"
)

type config struct {
	databaseURL string
	natsURL     string
	batchSize   int
}

func loadConfig() (config, error) {
	databaseURL := os.Getenv("TRAMA_DATABASE_URL")
	if databaseURL == "" {
		return config{}, fmt.Errorf("TRAMA_DATABASE_URL is required")
	}
	batchSize := 100
	if raw := os.Getenv("TRAMA_OUTBOX_BATCH_SIZE"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed < 1 {
			return config{}, fmt.Errorf("TRAMA_OUTBOX_BATCH_SIZE must be positive")
		}
		batchSize = parsed
	}
	natsURL := os.Getenv("TRAMA_NATS_URL")
	if natsURL == "" {
		natsURL = "nats://127.0.0.1:4222"
	}
	return config{databaseURL: databaseURL, natsURL: natsURL, batchSize: batchSize}, nil
}

func main() {
	configuration, err := loadConfig()
	if err != nil {
		log.Fatal(err)
	}
	database, err := sql.Open("pgx", configuration.databaseURL)
	if err != nil {
		log.Fatalf("open database: %v", err)
	}
	defer database.Close()
	if err := database.Ping(); err != nil {
		log.Fatalf("connect database: %v", err)
	}

	connection, err := nats.Connect(configuration.natsURL)
	if err != nil {
		log.Fatalf("connect NATS: %v", err)
	}
	defer connection.Drain()
	jetstream, err := connection.JetStream()
	if err != nil {
		log.Fatalf("open JetStream: %v", err)
	}
	if err := ensureStream(jetstream); err != nil {
		log.Fatalf("ensure task stream: %v", err)
	}

	worker := outbox.NewWorker(
		outbox.NewPostgresStore(database),
		outbox.NewNATSPublisher(jetstream),
	)
	ctx, stop := signal.NotifyContext(context.Background(), os.Interrupt, syscall.SIGTERM)
	defer stop()
	ticker := time.NewTicker(250 * time.Millisecond)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			if _, err := worker.PublishPending(ctx, configuration.batchSize); err != nil {
				log.Printf("publish outbox: %v", err)
			}
		}
	}
}

func ensureStream(stream nats.JetStreamContext) error {
	if _, err := stream.StreamInfo("TRAMA_EVENTS"); err == nil {
		return nil
	}
	_, err := stream.AddStream(&nats.StreamConfig{
		Name:      "TRAMA_EVENTS",
		Subjects:  []string{"trama.>"},
		Storage:   nats.FileStorage,
		Retention: nats.LimitsPolicy,
		MaxAge:    7 * 24 * time.Hour,
		Replicas:  1,
	})
	if err != nil && !errors.Is(err, nats.ErrStreamNameAlreadyInUse) {
		return err
	}
	return nil
}
