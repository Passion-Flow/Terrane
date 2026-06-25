// Package config — terrane-gateway configuration (stage 1: License gating + service listener).
// Environment variables are prefixed TERRANE_; licenses/ is a volume shared with the control plane.
package config

import (
	"os"
	"strconv"
	"strings"
)

type Config struct {
	Host     string
	Port     int
	LogLevel string

	// LicenseRequired is the master gating switch: the open-source build defaults to false, so the
	// data plane always passes traffic through (appears permanently activated). A commercial
	// deployment sets LICENSE_REQUIRED=true to restore Forge signature gating (the verification
	// code is fully retained and reversible).
	LicenseRequired bool

	LicensePath         string // activation envelope (written by the admin backend; shared across containers)
	LicenseStatePath    string // anti-rollback watermark (held independently by this component, separate from the control plane to avoid cross-contamination)
	LicenseCRLPath      string
	LicenseRecheckSecs  int
	LicenseCRLMaxAgeDay int // 0 = do not enforce CRL freshness
	ForgeEdgeURL        string
}

func env(key, def string) string {
	if v := os.Getenv(key); v != "" {
		return v
	}
	return def
}

func envBool(key string, def bool) bool {
	if v := os.Getenv(key); v != "" {
		switch strings.ToLower(strings.TrimSpace(v)) {
		case "1", "true", "yes", "on":
			return true
		case "0", "false", "no", "off":
			return false
		}
	}
	return def
}

func envInt(key string, def int) int {
	if v := os.Getenv(key); v != "" {
		if n, err := strconv.Atoi(v); err == nil {
			return n
		}
	}
	return def
}

func Load() Config {
	return Config{
		Host:     env("TERRANE_GATEWAY_HOST", "0.0.0.0"),
		Port:     envInt("TERRANE_GATEWAY_PORT", 43080),
		LogLevel: env("TERRANE_LOG_LEVEL", "INFO"),

		LicenseRequired: envBool("LICENSE_REQUIRED", false),

		LicensePath:         env("TERRANE_LICENSE_PATH", "licenses/active.forge"),
		LicenseStatePath:    env("TERRANE_LICENSE_STATE_PATH", "licenses/verifier_state_gateway.json"),
		LicenseCRLPath:      env("TERRANE_LICENSE_CRL_PATH", "licenses/crl.forge"),
		LicenseRecheckSecs:  envInt("TERRANE_LICENSE_RECHECK_SECONDS", 10),
		LicenseCRLMaxAgeDay: envInt("TERRANE_LICENSE_CRL_MAX_AGE_DAYS", 0),
		ForgeEdgeURL:        env("TERRANE_FORGE_EDGE_URL", ""),
	}
}
