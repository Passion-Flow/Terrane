package forge

import (
	"errors"
	"os"
	"path/filepath"
)

// ForgeVerifier — the high-level embeddable license check.
//
//	fv := forge.New("https://forge.navtra.ai")
//	fmt.Println("Deployment ID:", fv.Fingerprint)   // show on activation page
//	v := fv.VerifyOffline(pastedBlob, nil)           // offline .forge
//	v := fv.ActivateOnline(pastedCode, "")           // online short code
//	if !v.Unlocked() { show(v.Message("zh-CN")) }    // 需要激活许可证.
type ForgeVerifier struct {
	masterPub    []byte
	edgePub      []byte
	Fingerprint  string
	InstallID    string            // 反克隆：首激活随机 id（与指纹双锁）
	DeploymentID string            // 注入的容器/集群权威身份（裸机为空）
	Signals      map[string]string // 多信号向量
	online       *OnlineClient
}

// New builds a verifier; pass edgeURL="" for offline-only products.
func New(edgeURL string) *ForgeVerifier {
	return NewWithInstallPath(edgeURL, "")
}

// NewWithInstallPath lets the consumer pin where the install_id persists (e.g. a shared volume).
func NewWithInstallPath(edgeURL, installIDPath string) *ForgeVerifier {
	if installIDPath == "" {
		home, _ := os.UserHomeDir()
		installIDPath = filepath.Join(home, ".config", "forge", "install_id")
	}
	// 回退：无注入 UID 时用部署指纹当 deployment_uid——同机多组件（server/admin/gateway）
	// 共享同一指纹 → edge 按 UID 去重为「一个部署一个席位」，消除多组件抢席位的 binding_mismatch
	// 横跳。指纹来自硬件不可注入，反克隆/防伪不削弱（克隆机指纹不同→UID 不同→照样被拒）。
	fingerprint := DeploymentFingerprint()
	deploymentUID := DeploymentUID()
	if deploymentUID == "" {
		deploymentUID = fingerprint
	}
	fv := &ForgeVerifier{
		masterPub:    MasterPublicPEM(),
		edgePub:      EdgeLeasePublicPEM(),
		Fingerprint:  fingerprint,
		InstallID:    EnsureInstallID(installIDPath),
		DeploymentID: deploymentUID,
		Signals:      CollectSignals(),
	}
	if edgeURL != "" {
		fv.online = NewOnlineClient(edgeURL, fv.edgePub)
	}
	return fv
}

func (fv *ForgeVerifier) VerifyOffline(blob string, revoked map[string]bool) Verdict {
	return VerifyOffline(blob, fv.masterPub, fv.Fingerprint, revoked)
}

// RevokedFromCRL verifies a signed CRL with the embedded master key and returns the revoked
// license_ids. An untrusted/invalid CRL is ignored (empty) — license expiry still guards.
func (fv *ForgeVerifier) RevokedFromCRL(crlBlob string) map[string]bool {
	out := map[string]bool{}
	valid, payload, err := ParseAndVerify(crlBlob, fv.masterPub)
	if err != nil || !valid || str(payload, "kind") != "crl" {
		return out
	}
	if list, ok := payload["revoked"].([]any); ok {
		for _, id := range list {
			if s, ok := id.(string); ok {
				out[s] = true
			}
		}
	}
	return out
}

func (fv *ForgeVerifier) ActivateOnline(onlineCode, clusterID string) (Verdict, error) {
	if fv.online == nil {
		return Verdict{}, errors.New("edgeURL not configured")
	}
	return fv.online.Activate(onlineCode, fv.Fingerprint, clusterID,
		fv.InstallID, fv.DeploymentID, fv.Signals), nil
}

func (fv *ForgeVerifier) Revalidate() (Verdict, error) {
	if fv.online == nil {
		return Verdict{}, errors.New("edgeURL not configured")
	}
	return fv.online.Revalidate(fv.Fingerprint, fv.InstallID), nil
}
