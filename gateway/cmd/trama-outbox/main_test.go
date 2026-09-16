package main

import "testing"

func TestOutboxConfigurationUsesSafeLocalDefaults(t *testing.T) {
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
}

func TestOutboxConfigurationRequiresPostgres(t *testing.T) {
	t.Setenv("TRAMA_DATABASE_URL", "")
	if _, err := loadConfig(); err == nil {
		t.Fatal("expected missing database URL to fail")
	}
}
