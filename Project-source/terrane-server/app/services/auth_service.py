"""Front-end user authentication service — registration (auto-creates a personal workspace) / login / email verification / password reset / password change.

Platform database terrane_main: users / workspaces / memberships. Email is globally unique within a deployment (enforced at the application layer).
Registration creates everything at once: a personal Workspace + User (status=pending, awaiting email verification) + Membership(Owner), and sends a verification email.
Enumeration-resistant: login and reset do not reveal whether a user exists. 2FA is a placeholder (implemented once KEK is wired up, consistent with admin).
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

    # ── Registration ──
    async def register(self, email: str, password: str, username: str | None,
                       *, base_url: str | None = None) -> User:
        email = email.lower()
        if await self.users.email_exists(email):
            raise BizError("AUTH_EMAIL_TAKEN")
        pol = await get_security_policy(self.db)  # Platform security policy (editable in admin under Settings -> Security)
        security.validate_password_policy(
            password, min_length=pol["password_min_length"], email=email,
            username=username or "", require_char_classes=pol["password_require_char_classes"],
            forbid_identity=self.settings.password_forbid_identity)

        display = username or email.split("@", 1)[0]
        ws = Workspace(slug=_slugify_email(email), name=f"{display}'s Space", kind="personal")
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
        """Prefer the access URL derived from the request (following the deployment's IP/domain), falling back to the configured frontend_base_url."""
        return (base_url or self.settings.frontend_base_url or "http://localhost:43000").rstrip("/")

    async def _send_verify(self, user: User, *, base_url: str | None = None) -> None:
        """Send the verification email (best-effort: an unconfigured mailer or send failure does not block registration, it only logs a warning)."""
        token = await token_service.issue(VERIFY_KIND, str(user.id),
                                          ttl_seconds=self.settings.email_verify_ttl_seconds)
        link = f"{self._link_base(base_url)}/verify-email?token={token}"
        cfg = await get_setting(self.db, EMAIL_KEY)
        if not cfg or not cfg.get("configured"):
            log.warning("email_not_configured", action="verify_email", user_id=str(user.id))
            return
        brand = (cfg.get("from_name") or "Terrane").strip()
        html = email_service.render_action_email(
            brand=brand, title="Verify your email", button_text="Verify email",
            intro=f"Welcome to {brand}. Click the button below to verify your email and activate your account. This link is valid for 24 hours.",
            link=link, note="This verification link will expire in 24 hours.")
        try:
            await email_service.send(cfg, to=user.email, subject=f"Verify your {brand} email",
                                     body=f"Welcome to {brand}. Click the link to verify your email (valid for 24 hours):\n{link}",
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

    # ── Login ──
    async def authenticate(self, email: str, password: str, code: str | None) -> User:
        email = email.lower()
        await self.rl.assert_not_locked(email)
        user = await self.users.get_by_email(email)
        valid = user is not None and security.verify_password(password, user.password_hash)
        if not user or not valid:
            pol = await get_security_policy(self.db)  # Platform security policy (editable in admin under Settings -> Security)
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
                ok = await self._consume_backup_code(user, code)   # Backup code fallback (single-use)
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
        """SSO login: return the user if they already exist (reject if disabled); otherwise create a user (active + verified, random password) + personal workspace + Owner."""
        email = email.lower()
        existing = await self.users.get_by_email(email)
        if existing is not None:
            if existing.status == "disabled":
                raise BizError("AUTH_ACCOUNT_DISABLED")
            return existing
        display = name or email.split("@")[0]
        ws = Workspace(slug=_slugify_email(email), name=f"{display}'s Space", kind="personal")
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

    # ── 2FA (TOTP; secret stored KEK-encrypted) ──
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
        """Generate and stash a new secret (encrypted), returning (secret, otpauth URI). It is only truly enabled once verify succeeds."""
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

    # ── Password reset ──
    async def request_reset(self, email: str, *, base_url: str | None = None) -> None:
        """Send the reset email (enumeration-resistant: silently succeeds whether or not the email exists)."""
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
            brand=brand, title="Reset your password", button_text="Reset password",
            intro="We received a request to reset the password for your account. Click the button below to set a new password. This link is valid for 2 hours.",
            link=link, note="For security, this reset link will expire in 2 hours and can only be used once.")
        try:
            await email_service.send(cfg, to=user.email, subject=f"Reset your {brand} password",
                                     body=f"Click the link to reset your password (valid for 2 hours):\n{link}", html=html)
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
