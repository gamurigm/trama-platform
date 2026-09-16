package auth

import (
	"context"
	"fmt"
	"strings"

	"github.com/coreos/go-oidc/v3/oidc"
)

type oidcClaims struct {
	Subject        string `json:"sub"`
	OrganizationID string `json:"organization_id"`
	OrgID          string `json:"org_id"`
	Scope          string `json:"scope"`
}

// OIDCValidator discovers the provider metadata and verifies signatures,
// issuer, audience and expiry through the provider's rotating JWKS.
type OIDCValidator struct {
	verifier *oidc.IDTokenVerifier
}

func NewOIDCValidator(ctx context.Context, issuer, audience string) (*OIDCValidator, error) {
	if issuer == "" || audience == "" {
		return nil, fmt.Errorf("oidc issuer and audience are required")
	}
	provider, err := oidc.NewProvider(ctx, issuer)
	if err != nil {
		return nil, fmt.Errorf("discover oidc provider: %w", err)
	}
	return &OIDCValidator{
		verifier: provider.Verifier(&oidc.Config{ClientID: audience}),
	}, nil
}

func (v *OIDCValidator) Validate(ctx context.Context, token string) (Principal, error) {
	idToken, err := v.verifier.Verify(ctx, token)
	if err != nil {
		return Principal{}, ErrUnauthorized
	}
	var claims oidcClaims
	if err := idToken.Claims(&claims); err != nil {
		return Principal{}, ErrUnauthorized
	}
	return principalFromClaims(claims)
}

func principalFromClaims(claims oidcClaims) (Principal, error) {
	organizationID := claims.OrganizationID
	if organizationID == "" {
		organizationID = claims.OrgID
	}
	if claims.Subject == "" || organizationID == "" {
		return Principal{}, ErrUnauthorized
	}
	return Principal{
		Subject:        claims.Subject,
		OrganizationID: organizationID,
		Scopes:         strings.Fields(claims.Scope),
	}, nil
}
