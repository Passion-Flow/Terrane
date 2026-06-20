package forge

import (
	"crypto/rand"
	"crypto/sha256"
	"encoding/hex"
	"net"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"runtime"
	"strings"
)

// Hardware fingerprint — stable per-deployment id collected live, never stored.
// Linux /etc/machine-id · macOS IOPlatformUUID · Windows MachineGuid · fallback hostname+MAC.

func firstMAC() string {
	ifaces, _ := net.Interfaces()
	for _, i := range ifaces {
		if i.Flags&net.FlagLoopback == 0 && i.HardwareAddr.String() != "" {
			return i.HardwareAddr.String()
		}
	}
	return "no-mac"
}

func rawMachineID() string {
	// SECURITY: deployment-UID override only under FORGE_SDK_DEV; production must use real hardware.
	if os.Getenv("FORGE_SDK_DEV") != "" {
		if v := os.Getenv("FORGE_DEPLOYMENT_UID"); v != "" {
			return "override:" + v
		}
	}
	// Production containers/K8s: the injected stable uid IS the deployment identity (per-pod
	// machine-ids are noise); offline binding mirrors the online activate path. Bare metal
	// ignores the env var (anti-spoof). Dev `override:` keeps its historic derivation.
	if v := os.Getenv("FORGE_DEPLOYMENT_UID"); v != "" && inContainer() {
		return "uid:" + v
	}
	switch runtime.GOOS {
	case "linux":
		for _, p := range []string{"/etc/machine-id", "/var/lib/dbus/machine-id"} {
			if b, err := os.ReadFile(p); err == nil {
				if v := strings.TrimSpace(string(b)); v != "" {
					return "linux:" + v
				}
			}
		}
	case "darwin":
		if out, err := exec.Command("ioreg", "-rd1", "-c", "IOPlatformExpertDevice").Output(); err == nil {
			if m := regexp.MustCompile(`IOPlatformUUID"?\s*=\s*"([^"]+)"`).FindSubmatch(out); m != nil {
				return "macos:" + string(m[1])
			}
		}
	case "windows":
		if out, err := exec.Command("reg", "query",
			`HKLM\SOFTWARE\Microsoft\Cryptography`, "/v", "MachineGuid").Output(); err == nil {
			if m := regexp.MustCompile(`MachineGuid\s+REG_SZ\s+([0-9a-fA-F-]+)`).FindSubmatch(out); m != nil {
				return "windows:" + string(m[1])
			}
		}
	}
	host, _ := os.Hostname()
	return "fallback:" + host + ":" + firstMAC()
}

// DeploymentFingerprint returns the SHA-256 hex shown on the product activation page.
func DeploymentFingerprint() string {
	sum := sha256.Sum256([]byte(rawMachineID()))
	return hex.EncodeToString(sum[:])
}

// ── anti-clone identity (design 07) — additive; DeploymentFingerprint() value unchanged ──

func inContainer() bool {
	if os.Getenv("KUBERNETES_SERVICE_HOST") != "" {
		return true
	}
	if _, err := os.Stat("/.dockerenv"); err == nil {
		return true
	}
	if b, err := os.ReadFile("/proc/1/cgroup"); err == nil {
		s := string(b)
		if strings.Contains(s, "docker") || strings.Contains(s, "kubepods") || strings.Contains(s, "containerd") {
			return true
		}
	}
	return false
}

// DeploymentUID returns an injected stable uid, authoritative ONLY in dev or inside a
// container/K8s (bare metal ignores it so a copier cannot spoof the bound id via env).
func DeploymentUID() string {
	uid := os.Getenv("FORGE_DEPLOYMENT_UID")
	if uid == "" {
		return ""
	}
	if os.Getenv("FORGE_SDK_DEV") != "" || inContainer() {
		return uid
	}
	return ""
}

func hashSig(v string) string {
	if v == "" {
		return ""
	}
	sum := sha256.Sum256([]byte(v))
	return hex.EncodeToString(sum[:])
}

func readTrim(path string) string {
	if b, err := os.ReadFile(path); err == nil {
		return strings.TrimSpace(string(b))
	}
	return ""
}

func machineIDRaw() string {
	switch runtime.GOOS {
	case "linux":
		for _, p := range []string{"/etc/machine-id", "/var/lib/dbus/machine-id"} {
			if v := readTrim(p); v != "" {
				return v
			}
		}
	case "darwin":
		if out, err := exec.Command("ioreg", "-rd1", "-c", "IOPlatformExpertDevice").Output(); err == nil {
			if m := regexp.MustCompile(`IOPlatformUUID"?\s*=\s*"([^"]+)"`).FindSubmatch(out); m != nil {
				return string(m[1])
			}
		}
	}
	return ""
}

// CollectSignals returns the multi-signal vector (each value hashed) for server-side fuzzy
// match & clone detection. Missing signals are omitted, never fabricated.
func CollectSignals() map[string]string {
	raw := map[string]string{
		"dmi_product_uuid": readTrim("/sys/class/dmi/id/product_uuid"),
		"board_serial":     readTrim("/sys/class/dmi/id/board_serial"),
		"disk_serial":      readTrim("/sys/class/dmi/id/product_serial"),
		"cpu_sig":          runtime.GOARCH + "|" + runtime.GOOS,
		"machine_id":       machineIDRaw(),
		"mac":              firstMAC(),
	}
	out := map[string]string{}
	for k, v := range raw {
		if v != "" && v != "no-mac" {
			out[k] = hashSig(v)
		}
	}
	return out
}

// EnsureInstallID returns a first-activation random id persisted 0600 at path. Stable across
// restarts; regenerated only when the file is gone (reinstall / fresh deploy = new identity).
func EnsureInstallID(path string) string {
	if v := readTrim(path); len(v) >= 16 {
		return v
	}
	buf := make([]byte, 32)
	if _, err := rand.Read(buf); err != nil {
		return ""
	}
	id := hex.EncodeToString(buf)
	if dir := filepath.Dir(path); dir != "" {
		_ = os.MkdirAll(dir, 0o700)
	}
	_ = os.WriteFile(path, []byte(id), 0o600)
	return id
}
