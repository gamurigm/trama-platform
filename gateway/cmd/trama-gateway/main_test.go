package main

import (
	"testing"
	"time"
)

func TestGatewayAddressDefaultsAndUsesTheEnvironmentOverride(t *testing.T) {
	t.Setenv("TRAMA_GATEWAY_ADDR", "")
	if got := gatewayAddress(); got != ":8080" {
		t.Fatalf("expected default address :8080, got %q", got)
	}

	t.Setenv("TRAMA_GATEWAY_ADDR", "127.0.0.1:9090")
	if got := gatewayAddress(); got != "127.0.0.1:9090" {
		t.Fatalf("expected configured address, got %q", got)
	}
}

func TestGatewayRateLimitHasSafeDefaultsAndCanBeConfigured(t *testing.T) {
	t.Setenv("TRAMA_GATEWAY_RATE_LIMIT", "1500")
	t.Setenv("TRAMA_GATEWAY_RATE_WINDOW_MS", "2000")

	limit, window, err := gatewayRateLimit()
	if err != nil {
		t.Fatalf("read rate limit: %v", err)
	}
	if limit != 1500 || window != 2*time.Second {
		t.Fatalf("unexpected rate limit %d / %s", limit, window)
	}
}

func TestGatewayAuthenticatorBuildsAServiceAccountValidator(t *testing.T) {
	t.Setenv("TRAMA_GATEWAY_SERVICE_ACCOUNT_TOKEN", "local-secret")
	t.Setenv("TRAMA_GATEWAY_SERVICE_ACCOUNT_ID", "outbox-worker")
	t.Setenv("TRAMA_GATEWAY_SERVICE_ACCOUNT_ORGANIZATION", "org-a")

	validator, required, err := gatewayAuthenticator()
	if err != nil {
		t.Fatalf("build authenticator: %v", err)
	}
	if required || validator == nil {
		t.Fatalf("expected optional configured service account, got %v / %#v", required, validator)
	}
}

func TestDatabasePoolHasBoundedSafeDefaultsAndCanBeConfigured(t *testing.T) {
	t.Setenv("TRAMA_DATABASE_MAX_OPEN_CONNS", "80")
	t.Setenv("TRAMA_DATABASE_MAX_IDLE_CONNS", "20")

	maxOpen, maxIdle, err := databasePoolConfig()
	if err != nil {
		t.Fatalf("read database pool config: %v", err)
	}
	if maxOpen != 80 || maxIdle != 20 {
		t.Fatalf("unexpected database pool config %d / %d", maxOpen, maxIdle)
	}
}
