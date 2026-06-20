"""统一业务错误 — BizError + {code, message, details, request_id} 信封。

注册表式（code → http_status/中文消息/log_level）；前台用 TRN_* + 认证 AUTH_* + 基础码。
阶段③接入 terrane-shared/error-codes.yaml 全量字典时迁出（保持 BizError API 不变）。
main.py 用 exc.http_status（property）+ exc.envelope(request_id)。
"""

from __future__ import annotations

from typing import Any

# code -> (http_status, 中文消息, log_level)
_CODES: dict[str, tuple[int, str, str]] = {
    # 认证
    "AUTH_REQUIRED": (401, "需要登录。", "info"),
    "AUTH_INVALID_CREDENTIALS": (401, "邮箱或密码错误。", "warning"),
    "AUTH_ACCOUNT_DISABLED": (403, "账号已被禁用。", "warning"),
    "AUTH_ACCOUNT_LOCKED": (429, "登录失败次数过多，账号已临时锁定。", "warning"),
    "AUTH_EMAIL_NOT_VERIFIED": (403, "邮箱尚未验证，请先完成邮箱验证。", "info"),
    "AUTH_2FA_REQUIRED": (401, "需要二次验证码。", "info"),
    "AUTH_2FA_INVALID": (401, "二次验证码无效。", "warning"),
    "AUTH_PASSWORD_WEAK": (400, "密码强度不满足策略要求。", "info"),
    "AUTH_PASSWORD_REUSED": (400, "新密码不能与当前密码相同。", "info"),
    "AUTH_EMAIL_TAKEN": (409, "该邮箱已被注册。", "info"),
    "AUTH_TOKEN_INVALID": (400, "链接无效或已过期。", "info"),
    # 权限
    "PERM_DENIED": (403, "无权限执行该操作。", "warning"),
    # 限流
    "RATE_LIMIT_EXCEEDED": (429, "请求过于频繁，请稍后再试。", "warning"),
    "RATE_LIMIT_LOGIN_BLOCKED": (429, "登录尝试过于频繁，请稍后再试。", "warning"),
    # 资源
    "RESOURCE_NOT_FOUND": (404, "资源不存在。", "info"),
    "RESOURCE_CONFLICT": (409, "资源冲突。", "info"),
    # 校验
    "VALIDATION_FAILED": (400, "请求参数校验失败。", "info"),
    # 系统
    "SYSTEM_NOT_IMPLEMENTED": (501, "该能力尚未实现。", "info"),
    "SYSTEM_UNAVAILABLE": (503, "该能力暂不可用。", "info"),
    # 许可证（与 License gate 信封对齐）
    "LICENSE_REQUIRED": (403, "需要激活许可证。", "info"),
}


class BizError(Exception):
    """业务代码唯一允许抛出的面向用户异常（HARD RULE：禁裸字符串/堆栈外泄）。"""

    def __init__(self, code: str, details: dict[str, Any] | None = None) -> None:
        if code not in _CODES:
            raise KeyError(f"error code '{code}' not registered in errors._CODES")
        self.code = code
        self.details = details or {}
        super().__init__(code)

    @property
    def http_status(self) -> int:
        return _CODES[self.code][0]

    @property
    def log_level(self) -> str:
        return _CODES[self.code][2]

    def message(self) -> str:
        return _CODES[self.code][1]

    def envelope(self, request_id: str) -> dict[str, Any]:
        return {
            "code": self.code,
            "message": self.message(),
            "details": self.details,
            "request_id": request_id,
        }


def all_codes() -> set[str]:
    return set(_CODES.keys())
