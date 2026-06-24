"""前台用户认证服务 — 注册（自动建个人工作区）/ 登录 / 邮箱验证 / 密码重置 / 改密。

平台库 terrane_main：users / workspaces / memberships。邮箱部署内全局唯一（应用层校验）。
注册即建：个人 Workspace + User（status=pending 待邮验）+ Membership(Owner)，发验证邮件。
防枚举：登录与重置对外不区分用户是否存在。2FA 占位（接 KEK 后落地，与 admin 一致）。
"""

from __future__ import annotations

import datetime
import secrets
import uuid

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import security
from app.core.config import get_settings
from app.core.errors import BizError
from app.models.membership import Membership
from app.models.user import User
from app.models.workspace import Workspace
from app.repositories.user import UserRepository
from app.services import email_service, token_service
from app.services.platform_settings import EMAIL_KEY, get_security_policy, get_setting
from app.services.ratelimit import RateLimiter

log = structlog.get_logger("terrane.auth")

VERIFY_KIND = "email_verify"
RESET_KIND = "pwd_reset"


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _slugify_email(email: str) -> str:
    local = email.split("@", 1)[0].lower()
    base = "".join(c if c.isalnum() else "-" for c in local).strip("-") or "ws"
    return f"{base[:40]}-{secrets.token_hex(3)}"


class AuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.users = UserRepository(db)
        self.rl = RateLimiter()
        self.settings = get_settings()

    # ── 注册 ──
    async def register(self, email: str, password: str, username: str | None,
                       *, base_url: str | None = None) -> User:
        email = email.lower()
        if await self.users.email_exists(email):
            raise BizError("AUTH_EMAIL_TAKEN")
        pol = await get_security_policy(self.db)  # 平台安全策略（后台「设置→安全」可改）
        security.validate_password_policy(
            password, min_length=pol["password_min_length"], email=email,
            username=username or "", require_char_classes=pol["password_require_char_classes"],
            forbid_identity=self.settings.password_forbid_identity)

        display = username or email.split("@", 1)[0]
        ws = Workspace(slug=_slugify_email(email), name=f"{display} 的空间", kind="personal")
        self.db.add(ws)
        await self.db.flush()
        user = User(workspace_id=ws.id, email=email, username=username,
                    password_hash=security.hash_password(password), status="pending")
        self.db.add(user)
        await self.db.flush()
        self.db.add(Membership(workspace_id=ws.id, user_id=user.id, role="Owner"))
        await self.db.commit()

        await self._send_verify(user, base_url=base_url)
        return user

    def _link_base(self, base_url: str | None) -> str:
        """优先用请求推导出的访问地址（跟随部署的 IP/域名），回退到配置的 frontend_base_url。"""
        return (base_url or self.settings.frontend_base_url or "http://localhost:43000").rstrip("/")

    async def _send_verify(self, user: User, *, base_url: str | None = None) -> None:
        """发验证邮件（best-effort：邮件未配置/发送失败不阻断注册，仅告警）。"""
        token = await token_service.issue(VERIFY_KIND, str(user.id),
                                          ttl_seconds=self.settings.email_verify_ttl_seconds)
        link = f"{self._link_base(base_url)}/verify-email?token={token}"
        cfg = await get_setting(self.db, EMAIL_KEY)
        if not cfg or not cfg.get("configured"):
            log.warning("email_not_configured", action="verify_email", user_id=str(user.id))
            return
        brand = (cfg.get("from_name") or "Terrane").strip()
        html = email_service.render_action_email(
            brand=brand, title="验证你的邮箱", button_text="验证邮箱",
            intro=f"欢迎加入 {brand}。点击下方按钮完成邮箱验证以激活你的账户，链接 24 小时内有效。",
            link=link, note="此验证链接将在 24 小时后失效。")
        try:
            await email_service.send(cfg, to=user.email, subject=f"验证你的 {brand} 邮箱",
                                     body=f"欢迎加入 {brand}。点击链接完成邮箱验证（24 小时内有效）：\n{link}",
                                     html=html)
        except BizError:
            log.warning("verify_email_send_failed", user_id=str(user.id))

    async def verify_email(self, token: str) -> User:
        user_id = await token_service.consume(VERIFY_KIND, token)
        if not user_id:
            raise BizError("AUTH_TOKEN_INVALID")
        user = await self.users.get(uuid.UUID(user_id))
        if not user:
            raise BizError("AUTH_TOKEN_INVALID")
        user.email_verified_at = _now()
        user.status = "active"
        await self.db.commit()
        return user

    # ── 登录 ──
    async def authenticate(self, email: str, password: str, code: str | None) -> User:
        email = email.lower()
        await self.rl.assert_not_locked(email)
        user = await self.users.get_by_email(email)
        valid = user is not None and security.verify_password(password, user.password_hash)
        if not user or not valid:
            pol = await get_security_policy(self.db)  # 平台安全策略（后台「设置→安全」可改）
            await self.rl.record_login_failure(
                email, threshold=pol["login_lock_threshold"], lock_seconds=pol["login_lock_seconds"])
            raise BizError("AUTH_INVALID_CREDENTIALS")
        if user.status == "disabled":
            raise BizError("AUTH_ACCOUNT_DISABLED")
        if user.email_verified_at is None or user.status == "pending":
            raise BizError("AUTH_EMAIL_NOT_VERIFIED")
        if user.twofa_enabled:
            if not code:
                raise BizError("AUTH_2FA_REQUIRED")
            from app.services import crypto, totp
            secret = crypto.decrypt(user.totp_secret_enc)
            ok = bool(secret) and totp.verify(secret, code)
            if not ok:
                ok = await self._consume_backup_code(user, code)   # 备份码兜底(一次性)
            if not ok:
                pol = await get_security_policy(self.db)
                await self.rl.record_login_failure(
                    email, threshold=pol["login_lock_threshold"], lock_seconds=pol["login_lock_seconds"])
                raise BizError("AUTH_2FA_INVALID")
        await self.rl.clear_login_failures(email)
        user.last_login_at = _now()
        await self.db.commit()
        return user

    async def provision_sso_user(self, email: str, name: str | None = None) -> User:
        """SSO 登录:已存在则返回(禁用则拒),否则建用户(active+已验证,随机密码)+个人工作区+Owner。"""
        email = email.lower()
        existing = await self.users.get_by_email(email)
        if existing is not None:
            if existing.status == "disabled":
                raise BizError("AUTH_ACCOUNT_DISABLED")
            return existing
        display = name or email.split("@")[0]
        ws = Workspace(slug=_slugify_email(email), name=f"{display} 的空间", kind="personal")
        self.db.add(ws)
        await self.db.flush()
        user = User(workspace_id=ws.id, email=email, username=display,
                    password_hash=security.hash_password(secrets.token_urlsafe(32)),
                    status="active", email_verified_at=_now())
        self.db.add(user)
        await self.db.flush()
        self.db.add(Membership(workspace_id=ws.id, user_id=user.id, role="Owner"))
        await self.db.commit()
        return user

    # ── 2FA（TOTP，secret 经 KEK 加密存储）──
    async def _consume_backup_code(self, user: User, code: str) -> bool:
        import json

        from app.services import crypto
        raw = crypto.decrypt(user.backup_codes_enc)
        if not raw:
            return False
        try:
            codes = json.loads(raw)
        except ValueError:
            return False
        c = (code or "").strip().lower()
        if c in codes:
            codes.remove(c)
            user.backup_codes_enc = crypto.encrypt(json.dumps(codes))
            await self.db.commit()
            return True
        return False

    async def twofa_begin(self, user: User) -> tuple[str, str]:
        """生成新 secret 暂存(加密),返回 (secret, otpauth URI)。verify 通过才真正启用。"""
        from app.services import crypto, totp
        secret = totp.gen_secret()
        user.totp_secret_enc = crypto.encrypt(secret)
        await self.db.commit()
        return secret, totp.provisioning_uri(secret, user.email)

    async def twofa_enable(self, user: User, code: str) -> list[str]:
        import json

        from app.services import crypto, totp
        secret = crypto.decrypt(user.totp_secret_enc)
        if not secret or not totp.verify(secret, code):
            raise BizError("AUTH_2FA_INVALID")
        backups = totp.gen_backup_codes()
        user.backup_codes_enc = crypto.encrypt(json.dumps(backups))
        user.twofa_enabled = True
        await self.db.commit()
        return backups

    async def twofa_disable(self, user: User, code: str) -> None:
        from app.services import crypto, totp
        secret = crypto.decrypt(user.totp_secret_enc)
        ok = (bool(secret) and totp.verify(secret, code)) or await self._consume_backup_code(user, code)
        if not ok:
            raise BizError("AUTH_2FA_INVALID")
        user.twofa_enabled = False
        user.totp_secret_enc = None
        user.backup_codes_enc = None
        await self.db.commit()

    # ── 密码重置 ──
    async def request_reset(self, email: str, *, base_url: str | None = None) -> None:
        """发重置邮件（防枚举：无论邮箱是否存在都静默成功）。"""
        user = await self.users.get_by_email(email.lower())
        if not user:
            return
        token = await token_service.issue(RESET_KIND, str(user.id),
                                          ttl_seconds=self.settings.password_reset_ttl_seconds)
        link = f"{self._link_base(base_url)}/reset-password?token={token}"
        cfg = await get_setting(self.db, EMAIL_KEY)
        if not cfg or not cfg.get("configured"):
            log.warning("email_not_configured", action="reset_password", user_id=str(user.id))
            return
        brand = (cfg.get("from_name") or "Terrane").strip()
        html = email_service.render_action_email(
            brand=brand, title="重置你的密码", button_text="重置密码",
            intro="我们收到了重置你账户密码的请求。点击下方按钮设置新密码，链接 2 小时内有效。",
            link=link, note="出于安全，此重置链接将在 2 小时后失效，且仅可使用一次。")
        try:
            await email_service.send(cfg, to=user.email, subject=f"重置你的 {brand} 密码",
                                     body=f"点击链接重置密码（2 小时内有效）：\n{link}", html=html)
        except BizError:
            log.warning("reset_email_send_failed", user_id=str(user.id))

    async def reset_password(self, token: str, new_password: str) -> User:
        user_id = await token_service.consume(RESET_KIND, token)
        if not user_id:
            raise BizError("AUTH_TOKEN_INVALID")
        user = await self.users.get(uuid.UUID(user_id))
        if not user:
            raise BizError("AUTH_TOKEN_INVALID")
        pol = await get_security_policy(self.db)
        security.validate_password_policy(
            new_password, min_length=pol["password_min_length"], email=user.email,
            username=user.username or "",
            require_char_classes=pol["password_require_char_classes"], forbid_identity=True)
        user.password_hash = security.hash_password(new_password)
        await self.db.commit()
        return user

    async def change_password(self, user: User, current_password: str, new_password: str) -> None:
        if not security.verify_password(current_password, user.password_hash):
            raise BizError("AUTH_INVALID_CREDENTIALS")
        pol = await get_security_policy(self.db)
        security.validate_password_policy(
            new_password, min_length=pol["password_min_length"], email=user.email,
            username=user.username or "",
            require_char_classes=pol["password_require_char_classes"], forbid_identity=True)
        if security.verify_password(new_password, user.password_hash):
            raise BizError("AUTH_PASSWORD_REUSED")
        user.password_hash = security.hash_password(new_password)
        await self.db.commit()
