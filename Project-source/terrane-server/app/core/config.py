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
    # 开源版默认关闭门控：license_required=False 时所有受保护接口直接放行、前端不显示激活/徽章。
    # 商业化部署设 LICENSE_REQUIRED=true 即恢复 Forge 验签门控（代码完整保留，可逆）。
    license_required: bool = False
    # install_id 与激活信封同放 licenses/ 共享卷：三组件共享同一部署身份（反克隆双锁）。
    terrane_license_path: str = "licenses/active.forge"
    terrane_license_state_path: str = "licenses/verifier_state.json"  # 反时钟回拨/CRL 防重放硬化
    terrane_license_crl_path: str = "licenses/crl.forge"
    terrane_license_recheck_seconds: int = 10
    terrane_license_crl_max_age_days: int = 0  # 0 = 不强制 CRL 新鲜度（离线气隙环境）
    terrane_forge_edge_url: str = ""           # 空 = 仅离线激活

    # —— 对象存储（字段化；provider 由 object_storage_type 选定；.agent.md [Service 使用情况]）——
    # 8 个 provider：local 双模 + s3 + 4 国产云(aliyun-oss/tencent-cos/volcengine-tos/huawei-obs)
    # + azure-blob + google-storage。自托管默认 = SeaweedFS（S3 兼容走 boto3）。
    object_storage_type: Literal[
        "local", "s3", "azure-blob", "aliyun-oss",
        "google-storage", "tencent-cos", "volcengine-tos", "huawei-obs",
    ] = "local"
    # local 双模：filesystem = 纯磁盘（开发默认）；s3 = 委托 SeaweedFS（S3 兼容端点）。
    object_storage_local_mode: Literal["filesystem", "s3"] = "filesystem"
    object_storage_local_path: str = "/var/lib/terrane/uploads"
    object_storage_default_bucket: str = "terrane"
    object_storage_presigned_url_expires: int = 900
    object_storage_max_file_size: int = 104857600
    # 通用云凭据（S3 / SeaweedFS / 阿里云 OSS / 腾讯 COS / 火山 TOS / 华为 OBS）。
    # endpoint 出厂留空，由 compose 注入本机 SeaweedFS S3 端点（48333）。
    object_storage_endpoint: str = ""          # 例 http://seaweedfs:48333 ；空 = provider 默认
    object_storage_region: str = ""
    object_storage_access_key: str = ""        # SeaweedFS 出厂用户 terrane_app（由 compose 注入）
    object_storage_secret_key: str = ""        # SeaweedFS 出厂密码 Seaweedfs@!QAZxsw2.（由 compose 注入）
    object_storage_secure: bool = True         # 端点 TLS
    # Azure Blob（account/key 模型，而非 access/secret）。
    object_storage_azure_account: str = ""
    object_storage_azure_key: str = ""
    # Google Cloud Storage（service-account JSON 路径 + project）。
    object_storage_gcs_credentials_json: str = ""
    object_storage_gcs_project: str = ""


@lru_cache
def get_settings() -> Settings:
    return Settings()
