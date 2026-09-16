// Package auth defines the authentication boundary of the gateway.
package auth

import (
	"context"
	"crypto/sha256"
	"encoding/hex"
	"errors"
	"net/http"
	"strings"
)

var ErrUnauthorized = errors.New("unauthorized")

type Principal struct {
	Subject        string
	OrganizationID string
	Scopes         []string
}

func HasScope(principal Principal, required string) bool {
	for _, scope := range principal.Scopes {
		if scope == required || scope == "*" {
			return true
		}
	}
	return false
}

type Validator interface {
	Validate(context.Context, string) (Principal, error)
}

type Chain []Validator

func (chain Chain) Validate(ctx context.Context, token string) (Principal, error) {
	for _, validator := range chain {
		principal, err := validator.Validate(ctx, token)
		if err == nil {
			return principal, nil
		}
	}
	return Principal{}, ErrUnauthorized
}

type contextKey struct{}

func PrincipalFromContext(ctx context.Context) (Principal, bool) {
	principal, ok := ctx.Value(contextKey{}).(Principal)
	return principal, ok
}

func Middleware(next http.Handler, validator Validator) http.Handler {
	return http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
		if request.URL.Path == "/health" {
			next.ServeHTTP(writer, request)
			return
		}
		const scheme = "bearer"
		authorization := request.Header.Get("Authorization")
		providedScheme, token, ok := strings.Cut(authorization, " ")
		if !ok || !strings.EqualFold(providedScheme, scheme) || strings.TrimSpace(token) == "" {
			unauthorized(writer)
			return
		}
		principal, err := validator.Validate(request.Context(), strings.TrimSpace(token))
		if err != nil || principal.Subject == "" || principal.OrganizationID == "" {
			unauthorized(writer)
			return
		}
		ctx := context.WithValue(request.Context(), contextKey{}, principal)
		next.ServeHTTP(writer, request.WithContext(ctx))
	})
}

func unauthorized(writer http.ResponseWriter) {
	writer.Header().Set("WWW-Authenticate", `Bearer realm="trama-gateway"`)
	http.Error(writer, "unauthorized", http.StatusUnauthorized)
}

// ServiceAccountValidator validates opaque service tokens without keeping the
// plaintext token in the process after configuration has been parsed.
type ServiceAccountValidator struct {
	accounts map[string]Principal
}

func NewServiceAccountValidator(accounts map[string]Principal) *ServiceAccountValidator {
	digests := make(map[string]Principal, len(accounts))
	for token, principal := range accounts {
		if token == "" {
			continue
		}
		digest := sha256.Sum256([]byte(token))
		digests[hex.EncodeToString(digest[:])] = Principal{
			Subject:        principal.Subject,
			OrganizationID: principal.OrganizationID,
			Scopes:         append([]string(nil), principal.Scopes...),
		}
	}
	return &ServiceAccountValidator{accounts: digests}
}

func (v *ServiceAccountValidator) Validate(_ context.Context, token string) (Principal, error) {
	digest := sha256.Sum256([]byte(token))
	principal, ok := v.accounts[hex.EncodeToString(digest[:])]
	if !ok {
		return Principal{}, ErrUnauthorized
	}
	principal.Scopes = append([]string(nil), principal.Scopes...)
	return principal, nil
}
