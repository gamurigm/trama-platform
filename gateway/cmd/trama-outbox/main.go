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
	"strings"
	"syscall"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
	"github.com/nats-io/nats.go"

	"github.com/gamur/trama/gateway/internal/outbox"
)

type config struct {
	databaseURL  string
	natsURL      string
	batchSize    int
	natsReplicas int
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
	natsReplicas := 1
	if strings.EqualFold(os.Getenv("TRAMA_ENV"), "prod") ||
		strings.EqualFold(os.Getenv("TRAMA_ENV"), "production") {
		natsReplicas = 3
	}
	if raw := os.Getenv("TRAMA_NATS_STREAM_REPLICAS"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed < 1 {
			return config{}, fmt.Errorf("TRAMA_NATS_STREAM_REPLICAS must be positive")
		}
		natsReplicas = parsed
	}
	return config{
		databaseURL:  databaseURL,
		natsURL:      natsURL,
		batchSize:    batchSize,
		natsReplicas: natsReplicas,
	}, nil
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
	if err := ensureStream(jetstream, configuration.natsReplicas); err != nil {
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

func ensureStream(stream nats.JetStreamContext, replicas int) error {
	if info, err := stream.StreamInfo("TRAMA_EVENTS"); err == nil {
		if info.Config.Replicas < replicas {
			return fmt.Errorf(
				"TRAMA_EVENTS has %d replicas; production requires at least %d",
				info.Config.Replicas,
				replicas,
			)
		}
		return nil
	}
	_, err := stream.AddStream(&nats.StreamConfig{
		Name:      "TRAMA_EVENTS",
		Subjects:  []string{"trama.>"},
		Storage:   nats.FileStorage,
		Retention: nats.LimitsPolicy,
		MaxAge:    7 * 24 * time.Hour,
		Replicas:  replicas,
	})
	if err != nil && !errors.Is(err, nats.ErrStreamNameAlreadyInUse) {
		return err
	}
	return nil
}
