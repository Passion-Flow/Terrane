// Package license — 数据面 License 状态机（多点防绕过的独立校验点：
// 即使控制面被篡改放行，数据面仍以内嵌公钥独立验签，fail-closed）。
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

type envelope struct {
	Method     string `json:"method"`
	Credential string `json:"credential"`
}

// Manager 持有当前 verdict；读多写少，RWMutex 保护。
type Manager struct {
	cfg           config.Config
	fv            *forge.ForgeVerifier
	mu            sync.RWMutex
	verdict       forge.Verdict
	ready         bool
	activatedCode string // 已成功激活的在线码；换码时必须重新激活而非续旧票
}

func NewManager(cfg config.Config) *Manager {
	// install_id 与激活信封同放 licenses/ 共享卷（design 02 反克隆）：与控制面共享同一身份。
	installPath := filepath.Join(filepath.Dir(cfg.LicensePath), "install_id")
	return &Manager{
		cfg:     cfg,
		fv:      forge.NewWithInstallPath(cfg.ForgeEdgeURL, installPath),
		verdict: forge.Verdict{Status: forge.StatusLocked, Reason: "not_activated"},
	}
}

func (m *Manager) Fingerprint() string { return m.fv.Fingerprint }

func (m *Manager) Verdict() forge.Verdict {
	m.mu.RLock()
	defer m.mu.RUnlock()
	return m.verdict
}

func (m *Manager) Unlocked() bool { return m.Verdict().Unlocked() }

func (m *Manager) Ready() bool {
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
	return envelope{Method: methodOffline, Credential: text}, true // 兼容裸 .forge blob
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

// VerifyNow 执行一次完整验签并更新状态；任何异常一律锁定（fail-closed）。
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
		// 同一个在线码 → 续期（断网在签名宽限期内放行）
		v, err := m.fv.Revalidate()
		if err != nil {
			return forge.Verdict{Status: forge.StatusLocked, Reason: "revalidate_error"}
		}
		return v
	}
	// 换了新码（如旧票被吊销后重新签发）→ 必须重新激活，绝不拿旧 token 续旧票
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

// Run 启动验签一次 + 周期复验，直到 ctx 取消。
func (m *Manager) Run(ctx context.Context) {
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
