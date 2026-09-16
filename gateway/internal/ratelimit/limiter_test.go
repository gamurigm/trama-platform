package ratelimit

import (
	"context"
	"testing"
	"time"

	"github.com/alicebob/miniredis/v2"
	"github.com/redis/go-redis/v9"
)

func TestMemoryLimiterAllowsTheConfiguredBurstAndReturnsRetryAfter(t *testing.T) {
	limiter := NewMemoryLimiter()
	ctx := context.Background()

	for attempt := 0; attempt < 2; attempt++ {
		decision, err := limiter.Allow(ctx, "org-a", 2, time.Second)
		if err != nil {
			t.Fatalf("allow request: %v", err)
		}
		if !decision.Allowed {
			t.Fatalf("expected request %d to be allowed", attempt+1)
		}
	}
	decision, err := limiter.Allow(ctx, "org-a", 2, time.Second)
	if err != nil {
		t.Fatalf("check exhausted limit: %v", err)
	}
	if decision.Allowed || decision.RetryAfter <= 0 {
		t.Fatalf("expected a retry delay after the burst, got %#v", decision)
	}

	other, err := limiter.Allow(ctx, "org-b", 2, time.Second)
	if err != nil || !other.Allowed {
		t.Fatalf("expected tenant-specific bucket, got %#v / %v", other, err)
	}
}

func TestRedisLimiterUsesAnAtomicBucket(t *testing.T) {
	server, err := miniredis.Run()
	if err != nil {
		t.Fatalf("start redis test server: %v", err)
	}
	defer server.Close()

	client := redis.NewClient(&redis.Options{Addr: server.Addr()})
	defer client.Close()
	limiter := NewRedisLimiter(client, "trama:test:rate")

	for attempt := 0; attempt < 2; attempt++ {
		decision, err := limiter.Allow(context.Background(), "org-a", 2, time.Minute)
		if err != nil || !decision.Allowed {
			t.Fatalf("expected redis request %d to be allowed: %#v / %v", attempt+1, decision, err)
		}
	}
	decision, err := limiter.Allow(context.Background(), "org-a", 2, time.Minute)
	if err != nil {
		t.Fatalf("check redis limit: %v", err)
	}
	if decision.Allowed || decision.RetryAfter <= 0 {
		t.Fatalf("expected redis bucket to reject burst: %#v", decision)
	}
	got, err := server.Get("trama:test:rate:org-a")
	if err != nil {
		t.Fatalf("read redis counter: %v", err)
	}
	if got != "3" {
		t.Fatalf("expected redis counter 3 after rejected attempt, got %q", got)
	}
}

func TestMemoryLimiterRejectsInvalidConfiguration(t *testing.T) {
	limiter := NewMemoryLimiter()
	if _, err := limiter.Allow(context.Background(), "org-a", 0, time.Second); err == nil {
		t.Fatal("expected zero limit to fail")
	}
	if _, err := limiter.Allow(context.Background(), "org-a", 1, 0); err == nil {
		t.Fatal("expected zero window to fail")
	}
}
