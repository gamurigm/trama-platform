package auth

import (
	"context"
	"net/http"
	"net/http/httptest"
	"testing"
)

type fakeValidator struct{}

func (fakeValidator) Validate(_ context.Context, token string) (Principal, error) {
	if token != "oidc-token" {
		return Principal{}, ErrUnauthorized
	}
	return Principal{Subject: "user-1", OrganizationID: "org-a", Scopes: []string{"tasks:write"}}, nil
}

func TestMiddlewareAuthenticatesBearerTokenAndExposesPrincipal(t *testing.T) {
	handler := Middleware(
		http.HandlerFunc(func(writer http.ResponseWriter, request *http.Request) {
			principal, ok := PrincipalFromContext(request.Context())
			if !ok || principal.Subject != "user-1" {
				t.Fatal("expected authenticated principal in request context")
			}
			writer.WriteHeader(http.StatusNoContent)
		}),
		fakeValidator{},
	)
	request := httptest.NewRequest(http.MethodGet, "/v1/tasks", nil)
	request.Header.Set("Authorization", "Bearer oidc-token")
	recorder := httptest.NewRecorder()

	handler.ServeHTTP(recorder, request)

	if recorder.Code != http.StatusNoContent {
		t.Fatalf("expected authenticated request, got %d", recorder.Code)
	}
}

func TestMiddlewareRejectsMissingOrMalformedCredentials(t *testing.T) {
	handler := Middleware(http.HandlerFunc(func(http.ResponseWriter, *http.Request) {
		t.Fatal("unauthenticated request reached handler")
	}), fakeValidator{})

	for _, authorization := range []string{"", "Basic abc", "Bearer"} {
		request := httptest.NewRequest(http.MethodGet, "/v1/tasks", nil)
		request.Header.Set("Authorization", authorization)
		recorder := httptest.NewRecorder()
		handler.ServeHTTP(recorder, request)
		if recorder.Code != http.StatusUnauthorized {
			t.Fatalf("expected 401 for %q, got %d", authorization, recorder.Code)
		}
	}
}

func TestServiceAccountValidatorStoresOnlyTokenDigestsAndScopesOrganization(t *testing.T) {
	validator := NewServiceAccountValidator(map[string]Principal{
		"service-secret": {Subject: "worker", OrganizationID: "org-a", Scopes: []string{"tasks:write"}},
	})

	principal, err := validator.Validate(context.Background(), "service-secret")
	if err != nil {
		t.Fatalf("validate service account: %v", err)
	}
	if principal.Subject != "worker" || principal.OrganizationID != "org-a" {
		t.Fatalf("unexpected service principal: %#v", principal)
	}
	if _, exists := validator.accounts["service-secret"]; exists {
		t.Fatal("service account validator must not retain plaintext token keys")
	}
}

func TestOIDCClaimsMapToARequiredTenantPrincipal(t *testing.T) {
	principal, err := principalFromClaims(oidcClaims{
		Subject:        "user-1",
		OrganizationID: "org-a",
		Scope:          "tasks:write tasks:read",
	})
	if err != nil {
		t.Fatalf("map oidc claims: %v", err)
	}
	if principal.Subject != "user-1" || principal.OrganizationID != "org-a" {
		t.Fatalf("unexpected oidc principal: %#v", principal)
	}
	if len(principal.Scopes) != 2 || principal.Scopes[1] != "tasks:read" {
		t.Fatalf("unexpected scopes: %#v", principal.Scopes)
	}
}
