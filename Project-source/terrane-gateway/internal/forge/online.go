package forge

import (
	"bytes"
	"encoding/json"
	"net/http"
	"time"
)

// OnlineClient phones home to forge-edge; lease + grace gives network resilience.
type OnlineClient struct {
	base      string
	edgePub   []byte
	client    *http.Client
	lastLease map[string]any
	token     string
}

func NewOnlineClient(edgeBaseURL string, edgeLeasePublicPEM []byte) *OnlineClient {
	return &OnlineClient{
		base:    trimSlash(edgeBaseURL),
		edgePub: edgeLeasePublicPEM,
		client:  &http.Client{Timeout: 8 * time.Second},
	}
}

func trimSlash(s string) string {
	for len(s) > 0 && s[len(s)-1] == '/' {
		s = s[:len(s)-1]
	}
	return s
}

// definitiveLockCodes — the authority DEFINITIVELY rejected this ticket → lock immediately,
// never ride the grace window. Grace only covers "no authoritative answer" (network/5xx).
var definitiveLockCodes = map[string]bool{
	"LICENSE_REVOKED": true, "LICENSE_EXPIRED": true, "LICENSE_BINDING_MISMATCH": true,
	"LICENSE_LEASE_EXPIRED": true, "RESOURCE_NOT_FOUND": true,
}

// graceOrLock rides the signed grace window if still within it, else locks. Non-definitive only.
func (c *OnlineClient) graceOrLock(reason string) Verdict {
	if c.lastLease != nil {
		if g := str(c.lastLease, "grace_until"); g != "" {
			if t, perr := time.Parse(time.RFC3339, g); perr == nil && time.Now().UTC().Before(t) {
				return Verdict{StatusActive, "grace", c.lastLease}
			}
		}
	}
	return Verdict{StatusLocked, reason, nil}
}

func (c *OnlineClient) post(path string, body map[string]any) (int, map[string]any, error) {
	b, _ := json.Marshal(body)
	resp, err := c.client.Post(c.base+path, "application/json", bytes.NewReader(b))
	if err != nil {
		return 0, nil, err
	}
	defer resp.Body.Close()
	var out map[string]any
	json.NewDecoder(resp.Body).Decode(&out)
	return resp.StatusCode, out, nil
}

func (c *OnlineClient) accept(resp map[string]any) Verdict {
	lt, _ := resp["lease_token"].(string)
	valid, lease, err := ParseAndVerify(lt, c.edgePub)
	if err != nil || !valid {
		return Verdict{StatusLocked, "lease_signature", nil}
	}
	c.lastLease = lease
	c.token, _ = resp["validation_token"].(string)
	return Verdict{StatusActive, "online", lease}
}

func (c *OnlineClient) Activate(onlineCode, fingerprint, clusterID, installID, deploymentUID string, signals map[string]string) Verdict {
	req := map[string]any{"online_code": onlineCode, "fingerprint": fingerprint, "cluster_id": clusterID}
	// Anti-clone identity fields (design 07): attach only when present; a newer edge can be
	// deployed first, and an older edge that doesn't receive them is unaffected.
	if installID != "" {
		req["install_id"] = installID
	}
	if deploymentUID != "" {
		req["deployment_uid"] = deploymentUID
	}
	if len(signals) > 0 {
		req["signals"] = signals
	}
	status, body, err := c.post("/edge/v1/activate", req)
	if err != nil {
		return Verdict{StatusLocked, "network", nil}
	}
	if status == 200 {
		return c.accept(body)
	}
	if str(body, "code") == "LICENSE_REVOKED" {
		return Verdict{StatusRevoked, "revoked", nil}
	}
	reason := str(body, "code")
	if reason == "" {
		reason = "activate_failed"
	}
	return Verdict{StatusLocked, reason, nil}
}

// Revalidate renews the lease. It distinguishes a DEFINITIVE authority rejection (revoked /
// expired / deleted / binding-mismatch / lease-gone → lock now, no grace) from a NON-authoritative
// outcome (connection failure / 5xx → ride the signed grace window).
func (c *OnlineClient) Revalidate(fingerprint, installID string) Verdict {
	if c.token == "" {
		return Verdict{StatusLocked, "not_activated", nil}
	}
	req := map[string]any{"validation_token": c.token, "fingerprint": fingerprint}
	if installID != "" {
		req["install_id"] = installID
	}
	status, body, err := c.post("/edge/v1/validate", req)
	if err != nil {
		return c.graceOrLock("network_error") // edge unreachable → grace
	}
	if status == 200 {
		return c.accept(body)
	}
	code := str(body, "code")
	if code == "LICENSE_REVOKED" {
		return Verdict{StatusRevoked, "revoked", nil} // definitive → lock now
	}
	if definitiveLockCodes[code] {
		return Verdict{StatusLocked, code, nil} // definitive → lock now (no grace)
	}
	if code == "" {
		code = "server_error"
	}
	return c.graceOrLock(code) // 5xx/unknown → grace
}
