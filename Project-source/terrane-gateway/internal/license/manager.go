// Package license — the data-plane License state machine (an independent checkpoint for defense
// in depth: even if the control plane is tampered with to pass traffic, the data plane still
// verifies independently with the embedded public key, fail-closed).
package license

import (
	"context"
	"encoding/json"
	"log/slog"
	"os"
	"path/filepath"
	"strings"
	"sync"
	"time"

	"github.com/navtra/terrane/gateway/internal/config"
	"github.com/navtra/terrane/gateway/internal/forge"
)

const (
	methodOffline = "offline"
	methodOnline  = "online"
)

// bypassVerdict — the synthetic unlocked verdict used when gating is disabled (open-source build);
// appears permanently activated.
var bypassVerdict = forge.Verdict{Status: forge.StatusActive, Reason: "license_not_required"}

type envelope struct {
	Method     string `json:"method"`
	Credential string `json:"credential"`
}

// Manager holds the current verdict; read-heavy and write-light, guarded by an RWMutex.
type Manager struct {
	cfg           config.Config
	fv            *forge.ForgeVerifier
	mu            sync.RWMutex
	verdict       forge.Verdict
	ready         bool
	activatedCode string // the online code that was successfully activated; switching codes must re-activate rather than renew the old ticket
}

func NewManager(cfg config.Config) *Manager {
	// install_id lives alongside the activation envelope in the shared licenses/ volume
	// (design 02 anti-clone): the same identity is shared with the control plane.
	installPath := filepath.Join(filepath.Dir(cfg.LicensePath), "install_id")
	return &Manager{
		cfg:     cfg,
		fv:      forge.NewWithInstallPath(cfg.ForgeEdgeURL, installPath),
		verdict: forge.Verdict{Status: forge.StatusLocked, Reason: "not_activated"},
	}
}

func (m *Manager) Fingerprint() string { return m.fv.Fingerprint }

// Required reports whether gating is enabled (open-source build defaults to false → always passes through).
func (m *Manager) Required() bool { return m.cfg.LicenseRequired }

func (m *Manager) Verdict() forge.Verdict {
	if !m.cfg.LicenseRequired {
		return bypassVerdict
	}
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.verdict
}

func (m *Manager) Unlocked() bool {
	if !m.cfg.LicenseRequired {
		return true
	}
	return m.Verdict().Unlocked()
}

func (m *Manager) Ready() bool {
	if !m.cfg.LicenseRequired {
		return true // gating disabled: ready without verification
	}
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.ready
}

func readEnvelope(path string) (envelope, bool) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return envelope{}, false
	}
	text := strings.TrimSpace(string(raw))
	if text == "" {
		return envelope{}, false
	}
	var env envelope
	if json.Unmarshal([]byte(text), &env) == nil &&
		(env.Method == methodOffline || env.Method == methodOnline) && env.Credential != "" {
		return env, true
	}
	return envelope{Method: methodOffline, Credential: text}, true // accept a bare .forge blob
}

func (m *Manager) loadCRL() (revoked map[string]bool, version *int, generatedAt string) {
	raw, err := os.ReadFile(m.cfg.LicenseCRLPath)
	if err != nil {
		return nil, nil, ""
	}
	blob := strings.TrimSpace(string(raw))
	if blob == "" {
		return nil, nil, ""
	}
	revoked = m.fv.RevokedFromCRL(blob)
	if valid, payload, e := forge.ParseAndVerify(blob, forge.MasterPublicPEM()); e == nil && valid {
		if kind, _ := payload["kind"].(string); kind == "crl" {
			if v, ok := payload["crl_version"].(float64); ok {
				n := int(v)
				version = &n
			}
			generatedAt, _ = payload["generated_at"].(string)
		}
	}
	return revoked, version, generatedAt
}

// VerifyNow runs one full verification pass and updates the state; any anomaly locks (fail-closed).
func (m *Manager) VerifyNow() forge.Verdict {
	env, ok := readEnvelope(m.cfg.LicensePath)
	var verdict forge.Verdict
	switch {
	case !ok:
		verdict = forge.Verdict{Status: forge.StatusLocked, Reason: "not_activated"}
	case env.Method == methodOnline:
		verdict = m.verifyOnline(env.Credential)
	default:
		verdict = m.verifyOffline(env.Credential)
	}

	m.mu.Lock()
	changed := verdict.Status != m.verdict.Status
	m.verdict = verdict
	m.ready = true
	m.mu.Unlock()
	if changed {
		slog.Info("license.status_changed", "status", verdict.Status, "reason", verdict.Reason)
	}
	return verdict
}

func (m *Manager) verifyOffline(blob string) forge.Verdict {
	revoked, crlVersion, crlGeneratedAt := m.loadCRL()
	opts := forge.VerifyOptions{
		Revoked:        revoked,
		StatePath:      m.cfg.LicenseStatePath,
		CRLVersion:     crlVersion,
		CRLGeneratedAt: crlGeneratedAt,
	}
	if m.cfg.LicenseCRLMaxAgeDay > 0 {
		maxAge := m.cfg.LicenseCRLMaxAgeDay
		opts.MaxCRLAgeDays = &maxAge
	}
	return forge.VerifyOfflineOpts(blob, forge.MasterPublicPEM(), m.fv.Fingerprint, opts)
}

func (m *Manager) verifyOnline(code string) forge.Verdict {
	if m.cfg.ForgeEdgeURL == "" {
		return forge.Verdict{Status: forge.StatusLocked, Reason: "edge_url_not_configured"}
	}
	m.mu.RLock()
	sameCode := code == m.activatedCode && m.activatedCode != ""
	m.mu.RUnlock()
	if sameCode {
		// Same online code → renew (when offline, pass within the signed grace window)
		v, err := m.fv.Revalidate()
		if err != nil {
			return forge.Verdict{Status: forge.StatusLocked, Reason: "revalidate_error"}
		}
		return v
	}
	// A new code (e.g. reissued after the old ticket was revoked) → must re-activate; never renew
	// the old ticket with the old token
	v, err := m.fv.ActivateOnline(code, "")
	if err != nil {
		return forge.Verdict{Status: forge.StatusLocked, Reason: "activate_error"}
	}
	if v.Unlocked() {
		m.mu.Lock()
		m.activatedCode = code
		m.mu.Unlock()
	}
	return v
}

// Run performs one verification at startup plus periodic re-verification until ctx is canceled.
func (m *Manager) Run(ctx context.Context) {
	if !m.cfg.LicenseRequired {
		slog.Info("license.disabled") // open-source build, gating off: no verification, no re-check loop
		return
	}
	v := m.VerifyNow()
	slog.Info("license.initial", "status", v.Status, "reason", v.Reason, "fingerprint", m.fv.Fingerprint)
	interval := time.Duration(max(m.cfg.LicenseRecheckSecs, 10)) * time.Second
	ticker := time.NewTicker(interval)
	defer ticker.Stop()
	for {
		select {
		case <-ctx.Done():
			return
		case <-ticker.C:
			m.VerifyNow()
		}
	}
}
