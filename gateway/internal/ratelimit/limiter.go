// Package ratelimit contains concurrency-safe admission throttles.
package ratelimit

import (
	"context"
	"fmt"
	"sync"
	"time"

	"github.com/redis/go-redis/v9"
)

type Decision struct {
	Allowed    bool
	RetryAfter time.Duration
}

type Limiter interface {
	Allow(context.Context, string, int, time.Duration) (Decision, error)
}

// MemoryLimiter is a local fallback for development and deterministic tests.
type MemoryLimiter struct {
	mu      sync.Mutex
	buckets map[string]bucket
}

type bucket struct {
	count     int
	expiresAt time.Time
}

func NewMemoryLimiter() *MemoryLimiter {
	return &MemoryLimiter{buckets: make(map[string]bucket)}
}

func (l *MemoryLimiter) Allow(
	ctx context.Context,
	key string,
	limit int,
	window time.Duration,
) (Decision, error) {
	if err := ctx.Err(); err != nil {
		return Decision{}, err
	}
	if key == "" || limit < 1 || window <= 0 {
		return Decision{}, fmt.Errorf("invalid rate limit configuration")
	}

	now := time.Now()
	l.mu.Lock()
	defer l.mu.Unlock()
	current, ok := l.buckets[key]
	if !ok || !now.Before(current.expiresAt) {
		l.buckets[key] = bucket{count: 1, expiresAt: now.Add(window)}
		return Decision{Allowed: true}, nil
	}
	if current.count >= limit {
		return Decision{RetryAfter: time.Until(current.expiresAt)}, nil
	}
	current.count++
	l.buckets[key] = current
	return Decision{Allowed: true}, nil
}

var fixedWindowScript = redis.NewScript(`
local current = redis.call("INCR", KEYS[1])
if current == 1 then
  redis.call("PEXPIRE", KEYS[1], ARGV[1])
end
return {current, redis.call("PTTL", KEYS[1])}
`)

// RedisLimiter shares the bucket across gateway replicas with one Lua
// operation, so concurrent replicas cannot race between INCR and EXPIRE.
type RedisLimiter struct {
	client redis.UniversalClient
	prefix string
}

func NewRedisLimiter(client redis.UniversalClient, prefix string) *RedisLimiter {
	return &RedisLimiter{client: client, prefix: prefix}
}

func (l *RedisLimiter) Allow(
	ctx context.Context,
	key string,
	limit int,
	window time.Duration,
) (Decision, error) {
	if key == "" || limit < 1 || window <= 0 {
		return Decision{}, fmt.Errorf("invalid rate limit configuration")
	}
	if err := ctx.Err(); err != nil {
		return Decision{}, err
	}
	result, err := fixedWindowScript.Run(
		ctx,
		l.client,
		[]string{l.prefix + ":" + key},
		window.Milliseconds(),
	).Result()
	if err != nil {
		return Decision{}, fmt.Errorf("run redis rate limit script: %w", err)
	}
	values, ok := result.([]interface{})
	if !ok || len(values) != 2 {
		return Decision{}, fmt.Errorf("redis rate limit script returned an invalid result")
	}
	current, ok := redisInt64(values[0])
	if !ok {
		return Decision{}, fmt.Errorf("redis rate limit count is invalid")
	}
	ttlMillis, ok := redisInt64(values[1])
	if !ok {
		return Decision{}, fmt.Errorf("redis rate limit ttl is invalid")
	}
	if current <= int64(limit) {
		return Decision{Allowed: true}, nil
	}
	if ttlMillis <= 0 {
		ttlMillis = window.Milliseconds()
	}
	return Decision{RetryAfter: time.Duration(ttlMillis) * time.Millisecond}, nil
}

func redisInt64(value interface{}) (int64, bool) {
	switch typed := value.(type) {
	case int64:
		return typed, true
	case int:
		return int64(typed), true
	case string:
		var parsed int64
		if _, err := fmt.Sscan(typed, &parsed); err != nil {
			return 0, false
		}
		return parsed, true
	default:
		return 0, false
	}
}
