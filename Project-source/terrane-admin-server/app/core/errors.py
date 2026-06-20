"""统一错误模型 — BizError + {code, message, details, request_id} 信封。

阶段②内置认证地基所需轻量码表（AUTH_*/PERM_*/RATE_*/RESOURCE_*/SYSTEM_*）。
阶段③接入 terrane-shared/error-codes.yaml 全量字典时迁出（保持 BizError API 不变）。
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
    # 向导
    "WIZARD_ALREADY_DONE": (409, "初始化向导已完成。", "info"),
    # 操作员管理
    "OPERATOR_SELF_FORBIDDEN": (400, "不能对当前登录的自己执行该操作。", "info"),
    "OPERATOR_LAST_SUPER_ADMIN": (400, "不能删除/禁用/降级最后一个超级管理员。", "info"),
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
