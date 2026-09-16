// Package httpapi exposes the public gateway boundary.
package httpapi

import (
	"context"
	"encoding/json"
	"errors"
	"net"
	"net/http"
	"net/http/httputil"
	"net/url"
	"strconv"
	"strings"
	"time"

	"github.com/gamur/trama/gateway/internal/admission"
	"github.com/gamur/trama/gateway/internal/auth"
	"github.com/gamur/trama/gateway/internal/ratelimit"
)

type Server struct {
	admission       *admission.Service
	limiter         ratelimit.Limiter
	rateLimit       int
	rateLimitWindow time.Duration
	authenticator   auth.Validator
	taskReader      admission.TaskReader
	controlPlane    http.Handler
	proxyError      error
	readyCheck      func(context.Context) error
}

type ServerOption func(*Server)

func WithRateLimit(limiter ratelimit.Limiter, limit int, window time.Duration) ServerOption {
	return func(server *Server) {
		server.limiter = limiter
		server.rateLimit = limit
		server.rateLimitWindow = window
	}
}

func WithAuthenticator(validator auth.Validator) ServerOption {
	return func(server *Server) {
		server.authenticator = validator
	}
}

func WithTaskReader(reader admission.TaskReader) ServerOption {
	return func(server *Server) {
		server.taskReader = reader
	}
}

func WithControlPlaneURL(rawURL string, internalToken string) ServerOption {
	return func(server *Server) {
		target, err := url.Parse(rawURL)
		if err != nil || target.Scheme == "" || target.Host == "" {
			server.proxyError = errors.New("control plane URL is invalid")
			return
		}
		proxy := httputil.NewSingleHostReverseProxy(target)
		originalDirector := proxy.Director
		proxy.Director = func(request *http.Request) {
			originalDirector(request)
			if principal, authenticated := auth.PrincipalFromContext(request.Context()); authenticated {
				request.Header.Set("X-Organization-ID", principal.OrganizationID)
				request.Header.Set("X-Actor-ID", principal.Subject)
				request.Header.Set("X-Scopes", strings.Join(principal.Scopes, " "))
				request.Header.Del("Authorization")
			}
			if internalToken != "" {
				request.Header.Set("X-Trama-Internal-Token", internalToken)
			}
		}
		proxy.ErrorHandler = func(writer http.ResponseWriter, _ *http.Request, err error) {
			writeJSON(writer, http.StatusBadGateway, errorResponse{
				Code: "control_plane_unavailable", Message: "Control plane is unavailable",
			})
		}
		server.controlPlane = proxy
	}
}

func WithReadinessCheck(check func(context.Context) error) ServerOption {
	return func(server *Server) {
		server.readyCheck = check
	}
}

func NewServer(admissionService *admission.Service, options ...ServerOption) http.Handler {
	server := Server{admission: admissionService}
	for _, option := range options {
		option(&server)
	}
	mux := http.NewServeMux()
	mux.HandleFunc("POST /v1/tasks", server.submitTask)
	mux.HandleFunc("GET /v1/tasks/{task_id}", server.getTask)
	if server.controlPlane != nil {
		mux.Handle("/v1/", http.HandlerFunc(server.forwardToControlPlane))
	}
	mux.HandleFunc("GET /health", health)
	mux.HandleFunc("GET /livez", live)
	mux.HandleFunc("GET /readyz", server.ready)
	if server.authenticator != nil {
		return auth.Middleware(mux, server.authenticator)
	}
	return mux
}

func (s Server) forwardToControlPlane(writer http.ResponseWriter, request *http.Request) {
	if s.controlPlane == nil {
		writeJSON(writer, http.StatusNotImplemented, errorResponse{
			Code: "control_plane_unavailable", Message: "Control plane proxy is not configured",
		})
		return
	}
	if principal, authenticated := auth.PrincipalFromContext(request.Context()); authenticated {
		requiredScope := proxyScope(request)
		if requiredScope != "" && !auth.HasScope(principal, requiredScope) {
			writeJSON(writer, http.StatusForbidden, errorResponse{
				Code: "insufficient_scope", Message: requiredScope + " scope is required",
			})
			return
		}
	}
	s.controlPlane.ServeHTTP(writer, request)
}

func proxyScope(request *http.Request) string {
	path := strings.TrimPrefix(request.URL.Path, "/v1/")
	resource, _, _ := strings.Cut(path, "/")
	if resource == "" {
		return ""
	}
	if request.Method == http.MethodGet || request.Method == http.MethodHead {
		return resource + ":read"
	}
	return resource + ":write"
}

func health(writer http.ResponseWriter, _ *http.Request) {
	writeJSON(writer, http.StatusOK, map[string]string{"service": "trama-gateway", "status": "ok"})
}

func live(writer http.ResponseWriter, _ *http.Request) {
	writeJSON(writer, http.StatusOK, map[string]string{"service": "trama-gateway", "status": "alive"})
}

func (s Server) ready(writer http.ResponseWriter, request *http.Request) {
	if s.readyCheck != nil {
		readyContext, cancel := context.WithTimeout(request.Context(), 2*time.Second)
		defer cancel()
		if err := s.readyCheck(readyContext); err != nil {
			writeJSON(writer, http.StatusServiceUnavailable, errorResponse{
				Code: "gateway_not_ready", Message: "Gateway dependencies are unavailable",
			})
			return
		}
	}
	if s.proxyError != nil {
		writeJSON(writer, http.StatusServiceUnavailable, errorResponse{
			Code: "control_plane_misconfigured", Message: "Control plane URL is invalid",
		})
		return
	}
	writeJSON(writer, http.StatusOK, map[string]string{"service": "trama-gateway", "status": "ready"})
}

func (s Server) submitTask(writer http.ResponseWriter, request *http.Request) {
	decoder := json.NewDecoder(http.MaxBytesReader(writer, request.Body, 1<<20))
	decoder.DisallowUnknownFields()
	var task admission.Task
	if err := decoder.Decode(&task); err != nil {
		writeJSON(writer, http.StatusBadRequest, errorResponse{Code: "invalid_task", Message: "Invalid task payload"})
		return
	}
	if s.limiter != nil {
		decision, err := s.limiter.Allow(
			request.Context(),
			task.OrganizationID+":"+clientKey(request),
			s.rateLimit,
			s.rateLimitWindow,
		)
		if err != nil {
			writeJSON(writer, http.StatusServiceUnavailable, errorResponse{
				Code: "rate_limit_unavailable", Message: "Rate limiting is temporarily unavailable",
			})
			return
		}
		if !decision.Allowed {
			retryAfter := int((decision.RetryAfter + time.Second - 1) / time.Second)
			if retryAfter < 1 {
				retryAfter = 1
			}
			writer.Header().Set("Retry-After", strconv.Itoa(retryAfter))
			writeJSON(writer, http.StatusTooManyRequests, errorResponse{
				Code: "rate_limited", Message: "Too many task admission requests",
			})
			return
		}
	}
	if principal, authenticated := auth.PrincipalFromContext(request.Context()); authenticated {
		if !auth.HasScope(principal, "tasks:write") {
			writeJSON(writer, http.StatusForbidden, errorResponse{
				Code: "insufficient_scope", Message: "tasks:write scope is required",
			})
			return
		}
		if principal.OrganizationID != task.OrganizationID {
			writeJSON(writer, http.StatusForbidden, errorResponse{
				Code: "organization_forbidden", Message: "task organization is not authorized",
			})
			return
		}
	}

	result, err := s.admission.Admit(request.Context(), task, request.Header.Get("Idempotency-Key"))
	if err != nil {
		status := http.StatusInternalServerError
		code := "admission_failed"
		message := "Task admission failed"
		if errors.Is(err, admission.ErrInvalidTask) || errors.Is(err, admission.ErrMissingIdempotencyKey) {
			status = http.StatusBadRequest
			code = "invalid_request"
			message = err.Error()
		} else if errors.Is(err, admission.ErrIdempotencyConflict) {
			status = http.StatusConflict
			code = "idempotency_conflict"
			message = err.Error()
		} else if errors.Is(err, admission.ErrTaskConflict) {
			status = http.StatusConflict
			code = "task_conflict"
			message = err.Error()
		}
		writeJSON(writer, status, errorResponse{Code: code, Message: message})
		return
	}

	writeJSON(writer, http.StatusAccepted, taskResponse{TaskID: result.TaskID, Status: result.Status})
}

func (s Server) getTask(writer http.ResponseWriter, request *http.Request) {
	if s.taskReader == nil {
		writeJSON(writer, http.StatusNotImplemented, errorResponse{
			Code: "task_reader_unavailable", Message: "Task projection is not configured",
		})
		return
	}
	organizationID := request.URL.Query().Get("organization_id")
	if principal, authenticated := auth.PrincipalFromContext(request.Context()); authenticated {
		if !auth.HasScope(principal, "tasks:read") && !auth.HasScope(principal, "tasks:write") {
			writeJSON(writer, http.StatusForbidden, errorResponse{
				Code: "insufficient_scope", Message: "tasks:read scope is required",
			})
			return
		}
		if organizationID != "" && organizationID != principal.OrganizationID {
			writeJSON(writer, http.StatusForbidden, errorResponse{
				Code: "organization_forbidden", Message: "task organization is not authorized",
			})
			return
		}
		organizationID = principal.OrganizationID
	}
	if organizationID == "" {
		writeJSON(writer, http.StatusBadRequest, errorResponse{
			Code: "organization_required", Message: "organization_id is required",
		})
		return
	}
	task, err := s.taskReader.GetTask(request.Context(), organizationID, request.PathValue("task_id"))
	if err != nil {
		if errors.Is(err, admission.ErrTaskNotFound) {
			writeJSON(writer, http.StatusNotFound, errorResponse{Code: "task_not_found", Message: err.Error()})
			return
		}
		writeJSON(writer, http.StatusInternalServerError, errorResponse{
			Code: "task_read_failed", Message: "Task projection could not be read",
		})
		return
	}
	writeJSON(writer, http.StatusOK, task)
}

func clientKey(request *http.Request) string {
	host, _, err := net.SplitHostPort(request.RemoteAddr)
	if err == nil && host != "" {
		return host
	}
	if request.RemoteAddr == "" {
		return "unknown"
	}
	return request.RemoteAddr
}

type taskResponse struct {
	TaskID string `json:"task_id"`
	Status string `json:"status"`
}

type errorResponse struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

func writeJSON(writer http.ResponseWriter, status int, body any) {
	writer.Header().Set("Content-Type", "application/json")
	writer.WriteHeader(status)
	_ = json.NewEncoder(writer).Encode(body)
}
