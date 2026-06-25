"""terrane-admin-api configuration — Stage 1 License gating + Stage 2 auth foundation (DB/Redis/Session).

Environment variable prefix `TERRANE_`; dual databases terrane_admin (admin operators) / terrane_main (platform DB, audit persistence).
In multi-container deployments, licenses/ is a shared volume (same volume as terrane-api / terrane-gateway).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    # —— Service ——
    terrane_host: str = "0.0.0.0"
    terrane_port: int = 43003
    terrane_log_level: str = "INFO"

    # —— Database (field-based DSN, no connection-string env; Xinchuang (domestic) matrix in db/dialects.py) ——
    database_type: str = "postgres"
    database_host: str = "postgres"
    database_port: int = 5432
    database_username: str = "terrane_app"
    database_password: str = "change-me"
    database_name: str = "terrane_admin"          # admin operator database
    database_ssl_mode: str = "prefer"
    database_pool_size: int = 20
    database_pool_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_echo: bool = False
    platform_database_name: str = "terrane_main"  # platform database (audit persistence, Stage 3)

    # —— Cache (Redis, split by logical database, caching.md) ——
    cache_host: str = "redis"
    cache_port: int = 6379
    cache_password: str = ""
    cache_use_ssl: bool = False
    cache_db_session: int = 1
    cache_db_ratelimit: int = 4
    cache_db_snapshot: int = 0
    cache_max_connections: int = 50

    # —— Session (server-side opaque record + HttpOnly cookie, authentication.md) ——
    session_cookie_name: str = "terrane_admin_session"
    session_absolute_ttl_seconds: int = 7 * 24 * 3600
    session_idle_ttl_seconds: int = 12 * 3600
    session_cookie_secure: bool = True
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # —— Password policy ——
    password_min_length: int = 12
    password_require_char_classes: int = 3
    password_forbid_identity: bool = False  # factory password = email must be usable → False

    # —— Login rate limiting / account lockout ——
    login_max_per_ip_per_min: int = 10
    login_lock_threshold: int = 5
    login_lock_seconds: int = 15 * 60

    # —— 2FA ——
    twofa_issuer: str = "Terrane"

    # —— License gating (the admin backend is the activation writer; server/gateway only read the same shared volume) ——
    # The open-source edition disables gating by default: when license_required=False, all protected endpoints pass through and the frontend shows no activation/badge.
    # Commercial deployments set LICENSE_REQUIRED=true to restore Forge signature-verification gating (the code is fully preserved and reversible).
    license_required: bool = False
    terrane_license_path: str = "licenses/active.forge"
    terrane_license_state_path: str = "licenses/verifier_state.json"
    terrane_license_crl_path: str = "licenses/crl.forge"
    terrane_license_recheck_seconds: int = 10
    terrane_license_crl_max_age_days: int = 0
    terrane_forge_edge_url: str = ""                     # empty = offline activation only
    terrane_activate_rate_limit_per_minute: int = 10     # activation endpoint per-IP rate limit (guards against brute-forcing signatures/short codes)


@lru_cache
def get_settings() -> Settings:
    return Settings()
