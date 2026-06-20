package license

import (
	"encoding/json"
	"os"
	"path/filepath"
	"testing"

	"github.com/navtra/terrane/gateway/internal/config"
	"github.com/navtra/terrane/gateway/internal/forge"
	"github.com/navtra/terrane/gateway/internal/forgetest"
)

func testManager(t *testing.T, issuer *forgetest.Issuer) (*Manager, string) {
	t.Helper()
	t.Setenv("FORGE_SDK_DEV", "1")
	t.Setenv("FORGE_EMBEDDED_KEYS", issuer.EmbeddedKeysJSON())
	dir := t.TempDir()
	cfg := config.Config{
		LicensePath:        filepath.Join(dir, "active.forge"),
		LicenseStatePath:   filepath.Join(dir, "verifier_state.json"),
		LicenseCRLPath:     filepath.Join(dir, "crl.forge"),
		LicenseRecheckSecs: 300,
	}
	return NewManager(cfg), cfg.LicensePath
}

func writeEnvelope(t *testing.T, path, method, credential string) {
	t.Helper()
	b, _ := json.Marshal(map[string]string{"method": method, "credential": credential})
	if err := os.WriteFile(path, b, 0o600); err != nil {
		t.Fatal(err)
	}
}

func TestLockedWithoutEnvelope(t *testing.T) {
	mgr, _ := testManager(t, forgetest.NewIssuer())
	v := mgr.VerifyNow()
	if v.Unlocked() || v.Reason != "not_activated" {
		t.Fatalf("expected locked not_activated, got %s/%s", v.Status, v.Reason)
	}
	if !mgr.Ready() {
		t.Fatal("manager must be ready after first verify (locked counts as ready)")
	}
}

func TestOfflineEnvelopeUnlocks(t *testing.T) {
	issuer := forgetest.NewIssuer()
	mgr, path := testManager(t, issuer)
	writeEnvelope(t, path, "offline", issuer.Issue(mgr.Fingerprint(), 365))
	if v := mgr.VerifyNow(); v.Status != forge.StatusActive {
		t.Fatalf("expected active, got %s/%s", v.Status, v.Reason)
	}
	if !mgr.Unlocked() {
		t.Fatal("expected unlocked")
	}
}

func TestTamperedSignatureLocked(t *testing.T) {
	issuer := forgetest.NewIssuer()
	mgr, path := testManager(t, issuer)
	blob := issuer.Issue(mgr.Fingerprint(), 365)
	tampered := blob[:len(blob)-2] + "xx"
	writeEnvelope(t, path, "offline", tampered)
	if v := mgr.VerifyNow(); v.Unlocked() {
		t.Fatalf("tampered blob must lock, got %s", v.Status)
	}
}

func TestBindingMismatchLocked(t *testing.T) {
	issuer := forgetest.NewIssuer()
	mgr, path := testManager(t, issuer)
	writeEnvelope(t, path, "offline", issuer.Issue("some-other-machine", 365))
	if v := mgr.VerifyNow(); v.Unlocked() {
		t.Fatalf("binding mismatch must lock, got %s", v.Status)
	}
}

func TestExpiredLocked(t *testing.T) {
	issuer := forgetest.NewIssuer()
	mgr, path := testManager(t, issuer)
	writeEnvelope(t, path, "offline", issuer.Issue(mgr.Fingerprint(), -1))
	if v := mgr.VerifyNow(); v.Unlocked() {
		t.Fatalf("expired must lock, got %s", v.Status)
	}
}
