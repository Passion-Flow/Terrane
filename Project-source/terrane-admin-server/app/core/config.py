"""terrane-admin-api 配置 — 阶段①License gating + 阶段②认证地基（DB/Redis/Session）。

环境变量前缀 `TERRANE_`；双库 terrane_admin（后台操作员）/ terrane_main（平台库，审计落地）。
多容器部署时 licenses/ 为共享卷（与 terrane-api / terrane-gateway 同卷）。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    # —— 服务 ——
    terrane_host: str = "0.0.0.0"
    terrane_port: int = 43003
    terrane_log_level: str = "INFO"

    # —— 数据库（字段化 DSN，禁 connection-string env；信创矩阵见 db/dialects.py）——
    database_type: str = "postgres"
    database_host: str = "postgres"
    database_port: int = 5432
    database_username: str = "terrane_app"
    database_password: str = "change-me"
    database_name: str = "terrane_admin"          # 后台操作员库
    database_ssl_mode: str = "prefer"
    database_pool_size: int = 20
    database_pool_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_echo: bool = False
    platform_database_name: str = "terrane_main"  # 平台库（审计落地，阶段③）

    # —— 缓存（Redis，逻辑库切分，caching.md）——
    cache_host: str = "redis"
    cache_port: int = 6379
    cache_password: str = ""
    cache_use_ssl: bool = False
    cache_db_session: int = 1
    cache_db_ratelimit: int = 4
    cache_db_snapshot: int = 0
    cache_max_connections: int = 50

    # —— Session（服务端不透明记录 + HttpOnly cookie，authentication.md）——
    session_cookie_name: str = "terrane_admin_session"
    session_absolute_ttl_seconds: int = 7 * 24 * 3600
    session_idle_ttl_seconds: int = 12 * 3600
    session_cookie_secure: bool = True
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # —— 密码策略 ——
    password_min_length: int = 12
    password_require_char_classes: int = 3
    password_forbid_identity: bool = False  # 出厂密码=邮箱要能用 → False

    # —— 登录限频 / 账号锁定 ——
    login_max_per_ip_per_min: int = 10
    login_lock_threshold: int = 5
    login_lock_seconds: int = 15 * 60

    # —— 2FA ——
    twofa_issuer: str = "Terrane"

    # —— License gating（后台是激活写入方；server/gateway 只读同一共享卷）——
    terrane_license_path: str = "licenses/active.forge"
    terrane_license_state_path: str = "licenses/verifier_state.json"
    terrane_license_crl_path: str = "licenses/crl.forge"
    terrane_license_recheck_seconds: int = 10
    terrane_license_crl_max_age_days: int = 0
    terrane_forge_edge_url: str = ""                     # 空 = 仅离线激活
    terrane_activate_rate_limit_per_minute: int = 10     # 激活接口每 IP 限频（防爆破签名/短码）


@lru_cache
def get_settings() -> Settings:
    return Settings()
