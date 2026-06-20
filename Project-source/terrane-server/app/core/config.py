"""terrane-api 配置 — 阶段①仅 License gating 所需（DB/Redis 等阶段②扩展）。

环境变量前缀 `TERRANE_`（.agent.md [认证/默认账号] / 项目独立）。
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    # —— 服务 ——
    terrane_host: str = "0.0.0.0"
    terrane_port: int = 43001
    terrane_log_level: str = "INFO"

    # —— 数据库（平台库 terrane_main；字段化 DSN，禁 connection-string env；信创矩阵见 db/dialects.py）——
    database_type: str = "postgres"
    database_host: str = "postgres"
    database_port: int = 5432
    database_username: str = "terrane_app"
    database_password: str = "change-me"
    database_name: str = "terrane_main"           # 前台平台库
    database_ssl_mode: str = "prefer"
    database_pool_size: int = 20
    database_pool_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_echo: bool = False

    # —— 缓存（Redis，逻辑库切分，caching.md §2）——
    cache_host: str = "redis"
    cache_port: int = 6379
    cache_password: str = ""
    cache_use_ssl: bool = False
    cache_db_session: int = 0          # 前台 Session（caching.md：db0=Session）
    cache_db_business: int = 1
    cache_db_ratelimit: int = 2        # 限流/登录锁定
    cache_db_tokens: int = 2           # 邮箱验证/重置一次性 token（与限流同库，前缀区分）
    cache_max_connections: int = 50

    # —— Session（服务端不透明记录 + HttpOnly cookie，authentication.md）——
    session_cookie_name: str = "terrane_session"
    session_absolute_ttl_seconds: int = 30 * 24 * 3600   # 前台用户绝对 TTL 更长
    session_idle_ttl_seconds: int = 7 * 24 * 3600
    session_cookie_secure: bool = True
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # —— 密码策略（前台用户：强制 forbid_identity）——
    password_min_length: int = 10
    password_require_char_classes: int = 2
    password_forbid_identity: bool = True

    # —— 登录限频 / 账号锁定 ——
    login_max_per_ip_per_min: int = 10
    login_lock_threshold: int = 5
    login_lock_seconds: int = 15 * 60

    # —— 注册 / 邮箱验证 / 密码重置 ——
    register_max_per_ip_per_hour: int = 10
    email_verify_ttl_seconds: int = 24 * 3600
    password_reset_ttl_seconds: int = 2 * 3600
    twofa_issuer: str = "Terrane"
    # 邮件中验证/重置链接的前台基址（页面化零配置：出厂指向本机前台）。
    frontend_base_url: str = "http://localhost:43000"

    # —— License gating（licensing.md / .agent.md [License gating]）——
    # install_id 与激活信封同放 licenses/ 共享卷：三组件共享同一部署身份（反克隆双锁）。
    terrane_license_path: str = "licenses/active.forge"
    terrane_license_state_path: str = "licenses/verifier_state.json"  # 反时钟回拨/CRL 防重放硬化
    terrane_license_crl_path: str = "licenses/crl.forge"
    terrane_license_recheck_seconds: int = 10
    terrane_license_crl_max_age_days: int = 0  # 0 = 不强制 CRL 新鲜度（离线气隙环境）
    terrane_forge_edge_url: str = ""           # 空 = 仅离线激活


@lru_cache
def get_settings() -> Settings:
    return Settings()
