// Package forge — Forge license Verifier SDK (Go). Embed in consumer products.
package forge

import (
	"crypto/ed25519"
	"crypto/x509"
	"encoding/base64"
	"encoding/json"
	"encoding/pem"
	"errors"
	"strings"
)

// Compact signed-token codec — MUST match forge-server app/licensing/forge_file.py.
// Format: <base64url(canonical_payload_json)>.<base64url(ed25519_signature)>

func parsePublicKey(pemBytes []byte) (ed25519.PublicKey, error) {
	block, _ := pem.Decode(pemBytes)
	if block == nil {
		return nil, errors.New("invalid PEM")
	}
	pub, err := x509.ParsePKIXPublicKey(block.Bytes)
	if err != nil {
		return nil, err
	}
	edpub, ok := pub.(ed25519.PublicKey)
	if !ok {
		return nil, errors.New("embedded key is not Ed25519")
	}
	return edpub, nil
}

// ParseAndVerify verifies the detached Ed25519 signature over the exact payload bytes.
func ParseAndVerify(blob string, publicPEM []byte) (bool, map[string]any, error) {
	parts := strings.Split(strings.TrimSpace(blob), ".")
	if len(parts) != 2 {
		return false, nil, errors.New("malformed token")
	}
	payloadBytes, err := base64.RawURLEncoding.DecodeString(parts[0])
	if err != nil {
		return false, nil, err
	}
	sig, err := base64.RawURLEncoding.DecodeString(parts[1])
	if err != nil {
		return false, nil, err
	}
	var payload map[string]any
	if err := json.Unmarshal(payloadBytes, &payload); err != nil {
		return false, nil, err
	}
	pub, err := parsePublicKey(publicPEM)
	if err != nil {
		return false, payload, err
	}
	return ed25519.Verify(pub, payloadBytes, sig), payload, nil
}
