package forge

import (
	_ "embed"
	"encoding/json"
	"os"
)

// Embedded vendor public keys. In a real product these are COMPILED IN via go:embed; the
// vendor bakes embedded_keys.json at SDK build time via `forge keys export-public`.
//
//go:embed embedded_keys.json
var embeddedKeys []byte

type keyEntry struct {
	KeyID     string `json:"key_id"`
	Alg       string `json:"alg"`
	PublicKey string `json:"public_key"`
}

type keySet struct {
	Master    keyEntry `json:"master"`
	EdgeLease keyEntry `json:"edge_lease"`
}

func loadKeys() keySet {
	raw := embeddedKeys
	// SECURITY: honor the env key-override ONLY under FORGE_SDK_DEV. The shipped binary embeds the
	// vendor key via go:embed; ignoring the override prevents swapping in an attacker key to verify
	// a self-signed license.
	if os.Getenv("FORGE_SDK_DEV") != "" {
		if env := os.Getenv("FORGE_EMBEDDED_KEYS"); env != "" {
			raw = []byte(env)
		}
	}
	var ks keySet
	json.Unmarshal(raw, &ks)
	return ks
}

func MasterPublicPEM() []byte    { return []byte(loadKeys().Master.PublicKey) }
func EdgeLeasePublicPEM() []byte { return []byte(loadKeys().EdgeLease.PublicKey) }
