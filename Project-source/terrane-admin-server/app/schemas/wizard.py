"""初始化向导 API schema（Pydantic v2 strict）。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, EmailStr, Field

_strict = ConfigDict(strict=True, extra="forbid")

Encryption = Literal["auto", "ssl", "starttls", "none"]


class EmailConfigIn(BaseModel):
    model_config = _strict
    host: str = Field(min_length=1, max_length=255)
    port: int = Field(ge=1, le=65535)
    encryption: Encryption = "auto"
    username: str = Field(default="", max_length=255)
    password: str = Field(default="", max_length=512)
    from_address: EmailStr
    from_name: str = Field(default="Terrane", max_length=120)
    allow_insecure: bool = False  # 内网自签证书放行（默认严格校验）


class EmailTestIn(BaseModel):
    model_config = _strict
    to: EmailStr


class EmailPresetOut(BaseModel):
    id: str
    label: str
    host: str
    port: int
    encryption: str
    from_locked: bool
    password_hint: str


class BrandingIn(BaseModel):
    model_config = _strict
    product_name: str = Field(min_length=1, max_length=120)
    logo_data: str | None = Field(default=None, max_length=1_000_000)   # 控制台/工作区 Logo（data URI/URL）
    login_logo: str | None = Field(default=None, max_length=1_000_000)  # 登录页 Logo
    favicon: str | None = Field(default=None, max_length=1_000_000)     # 站点 favicon
    accent_color: str = Field(min_length=4, max_length=16)
    login_subtitle: str | None = Field(default=None, max_length=255)
    support_url: str | None = Field(default=None, max_length=512)


class StepOut(BaseModel):
    key: str
    status: str  # done | current | pending


class EmailStateOut(BaseModel):
    configured: bool
    host: str
    port: int
    encryption: str
    username: str
    from_address: str
    from_name: str
    allow_insecure: bool
    has_password: bool


class BrandingOut(BaseModel):
    product_name: str
    logo_data: str | None = None
    accent_color: str
    login_subtitle: str | None = None
    support_url: str | None = None
    enabled: bool


class WizardStateOut(BaseModel):
    completed: bool
    steps: list[StepOut]
    email: EmailStateOut
    branding: BrandingOut
    email_presets: list[EmailPresetOut]
