"""认证 API schema — Pydantic v2 strict（照搬 Forge app/schemas/auth.py）。"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field

_strict = ConfigDict(strict=True, extra="forbid")


class LoginRequest(BaseModel):
    model_config = _strict
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    code: str | None = Field(default=None, max_length=8)  # 2FA TOTP


class ChangePasswordRequest(BaseModel):
    model_config = _strict
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    username: str
    role: str
    avatar: str | None = None
    twofa_enabled: bool
    must_change_password: bool = False
    permissions: list[str]
