// Package config — terrane-gateway 配置（阶段①：License gating + 服务监听）。
// 环境变量前缀 TERRANE_；licenses/ 为与控制面共享的卷。
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

	// LicenseRequired 门控总开关：开源版默认 false → 数据面全程放行（表现为始终已激活）；
	// 商业化部署设 LICENSE_REQUIRED=true 即恢复 Forge 验签门控（验签代码完整保留，可逆）。
	LicenseRequired bool

	LicensePath         string // 激活信封（后台管理端写入；多容器共享卷）
	LicenseStatePath    string // 验签防回拨水位（本组件独立持有，与控制面分开防互相污染）
	LicenseCRLPath      string
	LicenseRecheckSecs  int
	LicenseCRLMaxAgeDay int // 0 = 不强制 CRL 新鲜度
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
