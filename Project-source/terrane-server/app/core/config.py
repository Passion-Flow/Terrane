"""terrane-api configuration -- in stage 1 only what License gating needs (DB/Redis etc. are added in stage 2).

Environment variable prefix `TERRANE_` (.agent.md [auth/default account] / project-independent).
"""

from __future__ import annotations

from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="", case_sensitive=False, extra="ignore")

    # -- Service --
    terrane_host: str = "0.0.0.0"
    terrane_port: int = 43001
    terrane_log_level: str = "INFO"

    # -- Database (platform DB terrane_main; field-based DSN, no connection-string env; Xinchuang (domestic) matrix in db/dialects.py) --
    database_type: str = "postgres"
    database_host: str = "postgres"
    database_port: int = 5432
    database_username: str = "terrane_app"
    database_password: str = "change-me"
    database_name: str = "terrane_main"           # frontend platform DB
    database_ssl_mode: str = "prefer"
    database_pool_size: int = 20
    database_pool_max_overflow: int = 10
    database_pool_timeout: int = 30
    database_echo: bool = False

    # -- Cache (Redis, logical-DB partitioning, caching.md §2) --
    cache_host: str = "redis"
    cache_port: int = 6379
    cache_password: str = ""
    cache_use_ssl: bool = False
    cache_db_session: int = 0          # frontend Session (caching.md: db0=Session)
    cache_db_business: int = 1
    cache_db_ratelimit: int = 2        # rate limiting / login lockout
    cache_db_tokens: int = 2           # email-verification/reset one-time tokens (same DB as rate limiting, distinguished by prefix)
    cache_max_connections: int = 50

    # -- Session (opaque server-side record + HttpOnly cookie, authentication.md) --
    session_cookie_name: str = "terrane_session"
    session_absolute_ttl_seconds: int = 30 * 24 * 3600   # frontend users get a longer absolute TTL
    session_idle_ttl_seconds: int = 7 * 24 * 3600
    session_cookie_secure: bool = True
    session_cookie_samesite: Literal["lax", "strict", "none"] = "lax"

    # -- Password policy (frontend users: forbid_identity enforced) --
    password_min_length: int = 10
    password_require_char_classes: int = 2
    password_forbid_identity: bool = True

    # -- Login rate limiting / account lockout --
    login_max_per_ip_per_min: int = 10
    login_lock_threshold: int = 5
    login_lock_seconds: int = 15 * 60

    # -- Registration / email verification / password reset --
    register_max_per_ip_per_hour: int = 10
    email_verify_ttl_seconds: int = 24 * 3600
    password_reset_ttl_seconds: int = 2 * 3600
    twofa_issuer: str = "Terrane"
    # Frontend base URL for verification/reset links in emails (page-based zero-config: ships pointing at the local frontend).
    frontend_base_url: str = "http://localhost:43000"

    # -- License gating (licensing.md / .agent.md [License gating]) --
    # Open-source edition disables gating by default: when license_required=False all protected endpoints pass through and the frontend shows no activation/badge.
    # Commercial deployments set LICENSE_REQUIRED=true to restore Forge signature-verification gating (the code is fully retained and reversible).
    license_required: bool = False
    # install_id and the activation envelope share the licenses/ shared volume: the three components share one deployment identity (dual-lock anti-clone).
    terrane_license_path: str = "licenses/active.forge"
    terrane_license_state_path: str = "licenses/verifier_state.json"  # anti-clock-rollback / CRL replay-prevention hardening
    terrane_license_crl_path: str = "licenses/crl.forge"
    terrane_license_recheck_seconds: int = 10
    terrane_license_crl_max_age_days: int = 0  # 0 = do not enforce CRL freshness (offline air-gapped environments)
    terrane_forge_edge_url: str = ""           # empty = offline activation only

    # -- Object storage (field-based; provider selected by object_storage_type; .agent.md [Service usage]) --
    # 8 providers: local dual-mode + s3 + 4 domestic clouds (aliyun-oss/tencent-cos/volcengine-tos/huawei-obs)
    # + azure-blob + google-storage. Self-hosted default = SeaweedFS (S3-compatible via boto3).
    object_storage_type: Literal[
        "local", "s3", "azure-blob", "aliyun-oss",
        "google-storage", "tencent-cos", "volcengine-tos", "huawei-obs",
    ] = "local"
    # local dual-mode: filesystem = plain disk (development default); s3 = delegate to SeaweedFS (S3-compatible endpoint).
    object_storage_local_mode: Literal["filesystem", "s3"] = "filesystem"
    object_storage_local_path: str = "/var/lib/terrane/uploads"
    object_storage_default_bucket: str = "terrane"
    object_storage_presigned_url_expires: int = 900
    object_storage_max_file_size: int = 104857600
    # Generic cloud credentials (S3 / SeaweedFS / Aliyun OSS / Tencent COS / Volcengine TOS / Huawei OBS).
    # endpoint ships empty, injected by compose with the local SeaweedFS S3 endpoint (48333).
    object_storage_endpoint: str = ""          # e.g. http://seaweedfs:48333 ; empty = provider default
    object_storage_region: str = ""
    object_storage_access_key: str = ""        # SeaweedFS factory user terrane_app (injected by compose)
    object_storage_secret_key: str = ""        # SeaweedFS factory password Seaweedfs@!QAZxsw2. (injected by compose)
    object_storage_secure: bool = True         # endpoint TLS
    # Azure Blob (account/key model, not access/secret).
    object_storage_azure_account: str = ""
    object_storage_azure_key: str = ""
    # Google Cloud Storage (service-account JSON path + project).
    object_storage_gcs_credentials_json: str = ""
    object_storage_gcs_project: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
