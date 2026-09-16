package httpapi

import (
	"bytes"
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
	"time"

	"github.com/gamur/trama/gateway/internal/admission"
	"github.com/gamur/trama/gateway/internal/auth"
	"github.com/gamur/trama/gateway/internal/ratelimit"
)

func TestSubmitTaskReturnsTheCompatibleAcceptedResponse(t *testing.T) {
	handler := NewServer(admission.NewService(admission.NewMemoryStore()))
	request := httptest.NewRequest(http.MethodPost, "/v1/tasks", bytes.NewBufferString(`{
        "task_id":"task-1",
        "organization_id":"org-a",
        "project_id":"demo",
        "repository":"https://example.test/demo",
        "objective":"Run tests",
        "actor":"hermes",
        "branch":"main",
        "worktree":"C:/work/demo",
        "acceptance_criteria":["tests pass"]
    }`))
	request.Header.Set("Content-Type", "application/json")
	request.Header.Set("Idempotency-Key", "request-1")
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusAccepted {
		t.Fatalf("expected status 202, got %d: %s", recorder.Code, recorder.Body.String())
	}
	if got, want := recorder.Body.String(), "{\"task_id\":\"task-1\",\"status\":\"accepted\"}\n"; got != want {
		t.Fatalf("expected %s, got %s", want, got)
	}
}

func TestSubmitTaskRejectsRequestsWithoutAnIdempotencyKey(t *testing.T) {
	handler := NewServer(admission.NewService(admission.NewMemoryStore()))
	request := httptest.NewRequest(http.MethodPost, "/v1/tasks", bytes.NewBufferString(`{
        "task_id":"task-1",
        "organization_id":"org-a",
        "project_id":"demo",
        "repository":"https://example.test/demo",
        "objective":"Run tests",
        "actor":"hermes",
        "branch":"main",
        "worktree":"C:/work/demo",
        "acceptance_criteria":["tests pass"]
    }`))
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusBadRequest {
		t.Fatalf("expected status 400, got %d: %s", recorder.Code, recorder.Body.String())
	}
}

func TestSubmitTaskRejectsAConflictingIdempotencyKey(t *testing.T) {
	handler := NewServer(admission.NewService(admission.NewMemoryStore()))
	first := httptest.NewRequest(http.MethodPost, "/v1/tasks", bytes.NewBufferString(`{
        "task_id":"task-1", "organization_id":"org-a", "project_id":"demo",
        "repository":"https://example.test/demo", "objective":"Run tests", "actor":"hermes",
        "branch":"main", "worktree":"C:/work/demo", "acceptance_criteria":["tests pass"]
    }`))
	first.Header.Set("Idempotency-Key", "request-1")
	handler.ServeHTTP(httptest.NewRecorder(), first)

	second := httptest.NewRequest(http.MethodPost, "/v1/tasks", bytes.NewBufferString(`{
        "task_id":"task-2", "organization_id":"org-a", "project_id":"demo",
        "repository":"https://example.test/demo", "objective":"Deploy", "actor":"hermes",
        "branch":"main", "worktree":"C:/work/demo", "acceptance_criteria":["deploy succeeds"]
    }`))
	second.Header.Set("Idempotency-Key", "request-1")
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, second)

	if recorder.Code != http.StatusConflict {
		t.Fatalf("expected status 409, got %d: %s", recorder.Code, recorder.Body.String())
	}
}

type denyingLimiter struct{}

func (denyingLimiter) Allow(context.Context, string, int, time.Duration) (ratelimit.Decision, error) {
	return ratelimit.Decision{RetryAfter: 2 * time.Second}, nil
}

type taskAuthValidator struct{}

func (taskAuthValidator) Validate(context.Context, string) (auth.Principal, error) {
	return auth.Principal{
		Subject:        "user-1",
		OrganizationID: "org-a",
		Scopes:         []string{"tasks:write"},
	}, nil
}

func TestSubmitTaskReturnsRetryableRateLimitResponse(t *testing.T) {
	handler := NewServer(
		admission.NewService(admission.NewMemoryStore()),
		WithRateLimit(denyingLimiter{}, 10, time.Minute),
	)
	request := httptest.NewRequest(http.MethodPost, "/v1/tasks", bytes.NewBufferString(`{
        "task_id":"task-1", "organization_id":"org-a", "project_id":"demo",
        "repository":"https://example.test/demo", "objective":"Run tests", "actor":"hermes",
        "branch":"main", "worktree":"C:/work/demo", "acceptance_criteria":["tests pass"]
    }`))
	request.Header.Set("Idempotency-Key", "request-1")
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusTooManyRequests {
		t.Fatalf("expected status 429, got %d: %s", recorder.Code, recorder.Body.String())
	}
	if got := recorder.Header().Get("Retry-After"); got != "2" {
		t.Fatalf("expected retry-after 2, got %q", got)
	}
}

func TestSubmitTaskRequiresTheAuthenticatedOrganizationAndWriteScope(t *testing.T) {
	handler := NewServer(
		admission.NewService(admission.NewMemoryStore()),
		WithAuthenticator(taskAuthValidator{}),
	)
	request := httptest.NewRequest(http.MethodPost, "/v1/tasks", bytes.NewBufferString(`{
        "task_id":"task-1", "organization_id":"org-b", "project_id":"demo",
        "repository":"https://example.test/demo", "objective":"Run tests", "actor":"hermes",
        "branch":"main", "worktree":"C:/work/demo", "acceptance_criteria":["tests pass"]
    }`))
	request.Header.Set("Authorization", "Bearer any")
	request.Header.Set("Idempotency-Key", "request-1")
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusForbidden {
		t.Fatalf("expected status 403 for cross-tenant task, got %d: %s", recorder.Code, recorder.Body.String())
	}
}

func TestGetTaskReadsTheCommittedProjectionWithReadYourWriteConsistency(t *testing.T) {
	store := admission.NewMemoryStore()
	handler := NewServer(
		admission.NewService(store),
		WithTaskReader(store),
	)
	post := httptest.NewRequest(http.MethodPost, "/v1/tasks", bytes.NewBufferString(`{
        "task_id":"task-1", "organization_id":"org-a", "project_id":"demo",
        "repository":"https://example.test/demo", "objective":"Run tests", "actor":"hermes",
        "branch":"main", "worktree":"C:/work/demo", "acceptance_criteria":["tests pass"]
    }`))
	post.Header.Set("Idempotency-Key", "request-1")
	handler.ServeHTTP(httptest.NewRecorder(), post)

	get := httptest.NewRequest(http.MethodGet, "/v1/tasks/task-1?organization_id=org-a", nil)
	recorder := httptest.NewRecorder()
	handler.ServeHTTP(recorder, get)

	if recorder.Code != http.StatusOK {
		t.Fatalf("expected status 200, got %d: %s", recorder.Code, recorder.Body.String())
	}
	if !bytes.Contains(recorder.Body.Bytes(), []byte(`"task_id":"task-1"`)) ||
		!bytes.Contains(recorder.Body.Bytes(), []byte(`"state":"accepted"`)) {
		t.Fatalf("expected committed task projection, got %s", recorder.Body.String())
	}
}
