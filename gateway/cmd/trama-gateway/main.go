package main

import (
	"context"
	"database/sql"
	"errors"
	"log"
	"net/http"
	"os"
	"os/signal"
	"strconv"
	"strings"
	"syscall"
	"time"

	_ "github.com/jackc/pgx/v5/stdlib"
	"github.com/redis/go-redis/v9"

	"github.com/gamur/trama/gateway/internal/admission"
	"github.com/gamur/trama/gateway/internal/auth"
	"github.com/gamur/trama/gateway/internal/httpapi"
	"github.com/gamur/trama/gateway/internal/ratelimit"
)

func main() {
	databaseURL := os.Getenv("TRAMA_DATABASE_URL")
	if databaseURL == "" {
		log.Fatal("TRAMA_DATABASE_URL is required")
	}
	database, err := sql.Open("pgx", databaseURL)
	if err != nil {
		log.Fatalf("open database: %v", err)
	}
	maxOpen, maxIdle, err := databasePoolConfig()
	if err != nil {
		log.Fatal(err)
	}
	database.SetMaxOpenConns(maxOpen)
	database.SetMaxIdleConns(maxIdle)
	database.SetConnMaxLifetime(30 * time.Minute)
	database.SetConnMaxIdleTime(5 * time.Minute)
	defer database.Close()
	if err := database.Ping(); err != nil {
		log.Fatalf("connect database: %v", err)
	}

	limit, window, err := gatewayRateLimit()
	if err != nil {
		log.Fatal(err)
	}
	var limiter ratelimit.Limiter = ratelimit.NewMemoryLimiter()
	var redisClient *redis.Client
	if redisURL := os.Getenv("TRAMA_REDIS_URL"); redisURL != "" {
		options, err := redis.ParseURL(redisURL)
		if err != nil {
			log.Fatalf("parse redis URL: %v", err)
		}
		redisClient = redis.NewClient(options)
		pingContext, cancel := context.WithTimeout(context.Background(), 5*time.Second)
		if err := redisClient.Ping(pingContext).Err(); err != nil {
			cancel()
			log.Fatalf("connect redis: %v", err)
		}
		cancel()
		limiter = ratelimit.NewRedisLimiter(redisClient, "trama:gateway:admission")
		defer redisClient.Close()
	} else {
		log.Printf("TRAMA_REDIS_URL is not configured; using a per-replica memory limiter")
	}
	validator, authRequired, err := gatewayAuthenticator()
	if err != nil {
		log.Fatal(err)
	}
	serverOptions := []httpapi.ServerOption{
		httpapi.WithRateLimit(limiter, limit, window),
	}
	if validator != nil {
		serverOptions = append(serverOptions, httpapi.WithAuthenticator(validator))
	} else if authRequired {
		log.Fatal("TRAMA_GATEWAY_AUTH_REQUIRED is true but no OIDC or service account validator is configured")
	} else {
		log.Printf("gateway authentication is disabled; set TRAMA_GATEWAY_AUTH_REQUIRED=true in production")
	}

	store := admission.NewPostgresStore(database)
	serverOptions = append(serverOptions, httpapi.WithTaskReader(store))
	server := &http.Server{
		Addr:              gatewayAddress(),
		Handler:           httpapi.NewServer(admission.NewService(store), serverOptions...),
		ReadHeaderTimeout: 5 * time.Second,
		ReadTimeout:       15 * time.Second,
		WriteTimeout:      30 * time.Second,
		IdleTimeout:       60 * time.Second,
	}
	go func() {
		log.Printf("TRAMA gateway listening on %s", server.Addr)
		if err := server.ListenAndServe(); err != nil && !errors.Is(err, http.ErrServerClosed) {
			log.Fatalf("serve gateway: %v", err)
		}
	}()

	signals := make(chan os.Signal, 1)
	signal.Notify(signals, os.Interrupt, syscall.SIGTERM)
	<-signals
	shutdown, cancel := context.WithTimeout(context.Background(), 10*time.Second)
	defer cancel()
	if err := server.Shutdown(shutdown); err != nil {
		log.Printf("shutdown gateway: %v", err)
	}
}

func gatewayAddress() string {
	if address := os.Getenv("TRAMA_GATEWAY_ADDR"); address != "" {
		return address
	}
	return ":8080"
}

func gatewayRateLimit() (int, time.Duration, error) {
	limit := 2000
	if raw := os.Getenv("TRAMA_GATEWAY_RATE_LIMIT"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed < 1 {
			return 0, 0, errors.New("TRAMA_GATEWAY_RATE_LIMIT must be a positive integer")
		}
		limit = parsed
	}
	windowMillis := 1000
	if raw := os.Getenv("TRAMA_GATEWAY_RATE_WINDOW_MS"); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed < 1 {
			return 0, 0, errors.New("TRAMA_GATEWAY_RATE_WINDOW_MS must be a positive integer")
		}
		windowMillis = parsed
	}
	return limit, time.Duration(windowMillis) * time.Millisecond, nil
}

func databasePoolConfig() (int, int, error) {
	maxOpen, err := positiveEnvInt("TRAMA_DATABASE_MAX_OPEN_CONNS", 64)
	if err != nil {
		return 0, 0, err
	}
	maxIdle, err := positiveEnvInt("TRAMA_DATABASE_MAX_IDLE_CONNS", 16)
	if err != nil {
		return 0, 0, err
	}
	if maxIdle > maxOpen {
		return 0, 0, errors.New("TRAMA_DATABASE_MAX_IDLE_CONNS cannot exceed max open connections")
	}
	return maxOpen, maxIdle, nil
}

func positiveEnvInt(name string, defaultValue int) (int, error) {
	value := defaultValue
	if raw := os.Getenv(name); raw != "" {
		parsed, err := strconv.Atoi(raw)
		if err != nil || parsed < 1 {
			return 0, errors.New(name + " must be a positive integer")
		}
		value = parsed
	}
	return value, nil
}

func gatewayAuthenticator() (auth.Validator, bool, error) {
	required := false
	if raw := os.Getenv("TRAMA_GATEWAY_AUTH_REQUIRED"); raw != "" {
		parsed, err := strconv.ParseBool(raw)
		if err != nil {
			return nil, false, errors.New("TRAMA_GATEWAY_AUTH_REQUIRED must be boolean")
		}
		required = parsed
	}

	validators := make([]auth.Validator, 0, 2)
	if token := os.Getenv("TRAMA_GATEWAY_SERVICE_ACCOUNT_TOKEN"); token != "" {
		organization := os.Getenv("TRAMA_GATEWAY_SERVICE_ACCOUNT_ORGANIZATION")
		if organization == "" {
			return nil, required, errors.New(
				"TRAMA_GATEWAY_SERVICE_ACCOUNT_ORGANIZATION is required with a service account token",
			)
		}
		subject := os.Getenv("TRAMA_GATEWAY_SERVICE_ACCOUNT_ID")
		if subject == "" {
			subject = "trama-service-account"
		}
		scopeText := os.Getenv("TRAMA_GATEWAY_SERVICE_ACCOUNT_SCOPES")
		if scopeText == "" {
			scopeText = "tasks:write"
		}
		validators = append(validators, auth.NewServiceAccountValidator(map[string]auth.Principal{
			token: {
				Subject:        subject,
				OrganizationID: organization,
				Scopes:         strings.FieldsFunc(scopeText, func(r rune) bool { return r == ',' || r == ' ' }),
			},
		}))
	}

	issuer := os.Getenv("TRAMA_GATEWAY_OIDC_ISSUER")
	audience := os.Getenv("TRAMA_GATEWAY_OIDC_AUDIENCE")
	if (issuer == "") != (audience == "") {
		return nil, required, errors.New(
			"TRAMA_GATEWAY_OIDC_ISSUER and TRAMA_GATEWAY_OIDC_AUDIENCE must be configured together",
		)
	}
	if issuer != "" {
		contextWithTimeout, cancel := context.WithTimeout(context.Background(), 10*time.Second)
		defer cancel()
		validator, err := auth.NewOIDCValidator(contextWithTimeout, issuer, audience)
		if err != nil {
			return nil, required, err
		}
		validators = append(validators, validator)
	}
	if len(validators) == 0 {
		return nil, required, nil
	}
	if len(validators) == 1 {
		return validators[0], required, nil
	}
	return auth.Chain(validators), required, nil
}
