// Package httpapi — data-plane HTTP entry point (stage 1: probes + License lock interception).
// Business routes (the six /v1/* endpoints) are wired in at stage 3.
package httpapi

import (
	"encoding/json"
	"net/http"

	"github.com/navtra/terrane/gateway/internal/license"
)

// openaiError — the unified outward-facing OpenAI-compatible error shape (03-api.md dual track:
// OpenAI-compatible externally / TRN_ internally).
type openaiError struct {
	Error struct {
		Message string `json:"message"`
		Type    string `json:"type"`
		Code    string `json:"code"`
	} `json:"error"`
}

func writeError(w http.ResponseWriter, status int, errType, code, message string) {
	var body openaiError
	body.Error.Message = message
	body.Error.Type = errType
	body.Error.Code = code
	w.Header().Set("Content-Type", "application/json")
	w.WriteHeader(status)
	_ = json.NewEncoder(w).Encode(body)
}

func NewHandler(mgr *license.Manager) http.Handler {
	mux := http.NewServeMux()

	mux.HandleFunc("GET /livez", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	mux.HandleFunc("GET /readyz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		if !mgr.Ready() {
			w.WriteHeader(http.StatusServiceUnavailable)
			_, _ = w.Write([]byte(`{"status":"starting"}`))
			return
		}
		_, _ = w.Write([]byte(`{"status":"ok"}`))
	})
	mux.HandleFunc("GET /healthz", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{
			"status": "ok", "license": mgr.Verdict().Status,
		})
	})

	// All other paths: 403 when locked (OpenAI-compatible); once unlocked, an unmatched business
	// route → 404. Independent data-plane verification = defense in depth: even if the control
	// plane is patched to pass traffic, this point still intercepts using the embedded public key.
	mux.HandleFunc("/", func(w http.ResponseWriter, r *http.Request) {
		if !mgr.Unlocked() {
			writeError(w, http.StatusForbidden, "forbidden",
				"TRN_LICENSE_LOCKED", "License activation required.")
			return
		}
		writeError(w, http.StatusNotFound, "invalid_request_error",
			"not_found", "Unknown request URL: "+r.URL.Path)
	})

	return mux
}
