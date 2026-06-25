"""Frontend authentication API schemas (Pydantic v2 strict)."""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, EmailStr, Field

_strict = ConfigDict(strict=True, extra="forbid")


class RegisterRequest(BaseModel):
    model_config = _strict
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    username: str | None = Field(default=None, max_length=64)


class LoginRequest(BaseModel):
    model_config = _strict
    email: EmailStr
    password: str = Field(min_length=1, max_length=256)
    code: str | None = Field(default=None, max_length=8)


class VerifyEmailRequest(BaseModel):
    model_config = _strict
    token: str = Field(min_length=1, max_length=256)


class RequestResetRequest(BaseModel):
    model_config = _strict
    email: EmailStr


class ResetPasswordRequest(BaseModel):
    model_config = _strict
    token: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class ChangePasswordRequest(BaseModel):
    model_config = _strict
    current_password: str = Field(min_length=1, max_length=256)
    new_password: str = Field(min_length=1, max_length=256)


class MeOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: str
    email: str
    username: str | None = None
    avatar: str | None = None
    status: str
    workspace_id: str
    role: str
    twofa_enabled: bool


class RegisterOut(BaseModel):
    id: str
    email: str
    status: str
    # Whether email verification is required after registration (always True out of the box).
    email_verification_required: bool = True
