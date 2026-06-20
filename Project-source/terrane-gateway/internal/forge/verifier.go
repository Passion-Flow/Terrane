package forge

import (
	"encoding/json"
	"os"
	"path/filepath"
	"time"
)

// VerifyOptions enables the anti-rollback hardening (set StatePath to a writable file the SDK owns).
type VerifyOptions struct {
	Revoked          map[string]bool // revoked license ids (from a CRL)
	Now              time.Time       // override the clock (zero => time.Now().UTC())
	StatePath        string          // persisted watermark + last CRL version/date; "" disables hardening
	CRLVersion       *int            // the consulted CRL's version (nil => not provided)
	CRLGeneratedAt   string          // the consulted CRL's generated_at (RFC3339)
	MaxCRLAgeDays    *int            // reject a CRL older than this many days (nil => no freshness check)
	ClockSkewMinutes int             // tolerated backward skew (0 => default 10)
}

type verifierState struct {
	TimeWatermark  string `json:"time_watermark,omitempty"`
	CRLVersion     int    `json:"crl_version,omitempty"`
	CRLGeneratedAt string `json:"crl_generated_at,omitempty"`
}

func loadState(path string) verifierState {
	var s verifierState
	if b, err := os.ReadFile(path); err == nil {
		_ = json.Unmarshal(b, &s)
	}
	return s
}

func saveState(path string, s verifierState) {
	// best-effort: a read-only FS can't be hardened, but never crash the product over it.
	if d := filepath.Dir(path); d != "" {
		_ = os.MkdirAll(d, 0o700)
	}
	if b, err := json.Marshal(s); err == nil {
		tmp := path + ".tmp"
		if os.WriteFile(tmp, b, 0o600) == nil {
			_ = os.Rename(tmp, path)
		}
	}
}

// Verdict statuses
const (
	StatusActive           = "active"
	StatusExpiring         = "expiring"
	StatusExpired          = "expired"
	StatusRevoked          = "revoked"
	StatusBindingMismatch  = "binding_mismatch"
	StatusInvalidSignature = "invalid_signature"
	StatusLocked           = "locked"
)

var lockMessage = map[string]string{"zh-CN": "需要激活许可证.", "en": "License activation required."}

// Verdict is the embeddable license check result. fail-closed: any anomaly => locked.
type Verdict struct {
	Status  string
	Reason  string
	Payload map[string]any
}

func (v Verdict) Unlocked() bool {
	return v.Status == StatusActive || v.Status == StatusExpiring
}

// Message returns the locked activation prompt for end users when not active.
func (v Verdict) Message(lang string) string {
	if v.Unlocked() {
		return ""
	}
	if m, ok := lockMessage[lang]; ok {
		return m
	}
	return lockMessage["en"]
}

func str(p map[string]any, k string) string {
	if s, ok := p[k].(string); ok {
		return s
	}
	return ""
}

// VerifyOffline checks a `.forge` token fully offline (signature + binding + expiry + CRL).
func VerifyOffline(blob string, masterPublicPEM []byte, localFingerprint string, revoked map[string]bool) Verdict {
	return VerifyOfflineOpts(blob, masterPublicPEM, localFingerprint, VerifyOptions{Revoked: revoked})
}

// VerifyOfflineOpts is VerifyOffline with anti-rollback hardening (clock watermark + CRL
// anti-rollback/freshness) when opts.StatePath points at a writable file the SDK owns.
func VerifyOfflineOpts(blob string, masterPublicPEM []byte, localFingerprint string, opts VerifyOptions) Verdict {
	now := opts.Now
	if now.IsZero() {
		now = time.Now().UTC()
	}
	valid, payload, err := ParseAndVerify(blob, masterPublicPEM)
	if err != nil {
		return Verdict{StatusLocked, "malformed", nil}
	}
	if !valid {
		return Verdict{StatusInvalidSignature, "signature", payload}
	}

	// --- anti-rollback hardening (state-backed) ---
	if opts.StatePath != "" {
		st := loadState(opts.StatePath)
		skew := opts.ClockSkewMinutes
		if skew == 0 {
			skew = 10
		}
		if st.TimeWatermark != "" {
			if wm, e := time.Parse(time.RFC3339, st.TimeWatermark); e == nil &&
				now.Before(wm.Add(-time.Duration(skew)*time.Minute)) {
				return Verdict{StatusLocked, "clock_rollback", payload}
			}
		}
		if opts.CRLVersion != nil && st.CRLVersion != 0 && *opts.CRLVersion < st.CRLVersion {
			return Verdict{StatusLocked, "crl_rollback", payload}
		}
		if opts.MaxCRLAgeDays != nil && opts.CRLGeneratedAt != "" {
			if gen, e := time.Parse(time.RFC3339, opts.CRLGeneratedAt); e == nil &&
				now.Sub(gen).Hours() > float64(*opts.MaxCRLAgeDays)*24 {
				return Verdict{StatusLocked, "crl_stale", payload}
			}
		}
		newWm := now
		if st.TimeWatermark != "" {
			if wm, e := time.Parse(time.RFC3339, st.TimeWatermark); e == nil && wm.After(newWm) {
				newWm = wm
			}
		}
		if opts.CRLGeneratedAt != "" {
			if gen, e := time.Parse(time.RFC3339, opts.CRLGeneratedAt); e == nil && gen.After(newWm) {
				newWm = gen
			}
		}
		st.TimeWatermark = newWm.UTC().Format(time.RFC3339)
		if opts.CRLVersion != nil && *opts.CRLVersion > st.CRLVersion {
			st.CRLVersion = *opts.CRLVersion
		}
		if opts.CRLGeneratedAt != "" {
			st.CRLGeneratedAt = opts.CRLGeneratedAt
		}
		saveState(opts.StatePath, st)
	}

	binding := str(payload, "binding")
	if binding == "" {
		binding = "hard"
	}
	if binding == "hard" && str(payload, "bound_fingerprint") != localFingerprint {
		return Verdict{StatusBindingMismatch, "fingerprint", payload}
	}
	if opts.Revoked != nil && opts.Revoked[str(payload, "license_id")] {
		return Verdict{StatusRevoked, "crl", payload}
	}
	if until := str(payload, "active_until"); until != "" {
		if t, perr := time.Parse(time.RFC3339, until); perr == nil {
			if !now.Before(t) {
				return Verdict{StatusExpired, "expired", payload}
			}
			if t.Sub(now).Hours() <= 30*24 {
				return Verdict{StatusExpiring, "expiring", payload}
			}
		}
	}
	return Verdict{StatusActive, "ok", payload}
}
