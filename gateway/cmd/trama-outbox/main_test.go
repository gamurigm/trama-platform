package main

import "testing"

func TestOutboxConfigurationUsesSafeLocalDefaults(t *testing.T) {
	t.Setenv("TRAMA_ENV", "local")
	t.Setenv("TRAMA_DATABASE_URL", "")
	t.Setenv("TRAMA_NATS_URL", "")
	t.Setenv("TRAMA_DATABASE_URL", "postgres://local/test")
	config, err := loadConfig()
	if err != nil {
		t.Fatalf("load defaults: %v", err)
	}
	if config.natsURL != "nats://127.0.0.1:4222" {
		t.Fatalf("unexpected NATS default: %q", config.natsURL)
	}
	if config.batchSize != 100 {
		t.Fatalf("unexpected batch default: %d", config.batchSize)
	}
	if config.natsReplicas != 1 {
		t.Fatalf("unexpected local NATS replica default: %d", config.natsReplicas)
	}
}

func TestOutboxConfigurationUsesDurableProductionNATSDefaults(t *testing.T) {
	t.Setenv("TRAMA_ENV", "prod")
	t.Setenv("TRAMA_DATABASE_URL", "postgres://local/test")
	t.Setenv("TRAMA_NATS_STREAM_REPLICAS", "")

	config, err := loadConfig()
	if err != nil {
		t.Fatalf("load production defaults: %v", err)
	}
	if config.natsReplicas != 3 {
		t.Fatalf("unexpected production NATS replica default: %d", config.natsReplicas)
	}
}

func TestOutboxConfigurationRequiresPostgres(t *testing.T) {
	t.Setenv("TRAMA_DATABASE_URL", "")
	if _, err := loadConfig(); err == nil {
		t.Fatal("expected missing database URL to fail")
	}
}
