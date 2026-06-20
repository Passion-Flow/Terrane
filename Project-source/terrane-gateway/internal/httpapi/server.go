// Package httpapi — 数据面 HTTP 入口（阶段①：探针 + License 锁定拦截）。
// 业务路由（/v1/* 六路收口）在阶段③接入。
package httpapi

import (
	"encoding/json"
	"net/http"

	"github.com/navtra/terrane/gateway/internal/license"
)

// openaiError — 对外统一 OpenAI 兼容错误结构（03-api.md 双轨：对外兼容 / 对内 TRN_）。
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

	// 其余一切路径：锁定态 403（OpenAI 兼容）；解锁后未匹配业务路由 → 404。
	// 数据面独立验签 = 多点防绕过：即便控制面被 patch 放行，此处仍以内嵌公钥拦截。
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
