// Package forgetest — test-only: generates a test master key and issues licenses in the
// Forge compact token format. Referenced only by _test.go files; never compiled into the
// shipped binary.
package forgetest

import (
	"crypto/ed25519"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"time"
)

type Issuer struct {
	priv      ed25519.PrivateKey
	PublicPEM string
}

func NewIssuer() *Issuer {
	pub, priv, err := ed25519.GenerateKey(nil)
	if err != nil {
		panic(err)
	}
	der, err := x509.MarshalPKIXPublicKey(pub)
	if err != nil {
		panic(err)
	}
	pemBytes := pem.EncodeToMemory(&pem.Block{Type: "PUBLIC KEY", Bytes: der})
	return &Issuer{priv: priv, PublicPEM: string(pemBytes)}
}

func (i *Issuer) EmbeddedKeysJSON() string {
	entry := map[string]string{"key_id": "test", "alg": "ed25519", "public_key": i.PublicPEM}
	b, _ := json.Marshal(map[string]any{"master": entry, "edge_lease": entry})
	return string(b)
}

func b64u(b []byte) string { return base64.RawURLEncoding.EncodeToString(b) }

// Sign issues an arbitrary payload in the <b64u(canonical_json)>.<b64u(sig)> format.
// canonical: keys sorted + compact separators (matching forge-server forge_file.py).
func (i *Issuer) Sign(payload map[string]any) string {
	b, err := canonicalJSON(payload)
	if err != nil {
		panic(err)
	}
	sig := ed25519.Sign(i.priv, b)
	return b64u(b) + "." + b64u(sig)
}

// Issue issues a standard test license bound to the given deployment fingerprint.
func (i *Issuer) Issue(fingerprint string, days int) string {
	now := time.Now().UTC()
	return i.Sign(map[string]any{
		"license_id":        "11112222-3333-4444-5555-666677778888",
		"customer":          "Test Customer Co., Ltd.",
		"product":           "terrane",
		"active_from":       now.Format(time.RFC3339),
		"active_until":      now.AddDate(0, 0, days).Format(time.RFC3339),
		"binding":           "hard",
		"bound_fingerprint": fingerprint,
		"alg":               "ed25519",
	})
}

// canonicalJSON — Go's encoding/json already sorts map keys; this drops HTML escaping and
// emits compact output.
func canonicalJSON(v any) ([]byte, error) {
	b, err := json.Marshal(v)
	if err != nil {
		return nil, err
	}
	return b, nil
}
