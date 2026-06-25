"""Unified business errors -- BizError + {code, message, details, request_id} envelope.

Registry-based (code -> http_status/message/log_level); the frontend uses TRN_* +
auth AUTH_* + base codes. To be migrated out in stage 3 when wiring up the full
terrane-shared/error-codes.yaml dictionary (the BizError API stays unchanged).
main.py uses exc.http_status (property) + exc.envelope(request_id).
"""

from __future__ import annotations

from typing import Any

# code -> (http_status, message, log_level)
_CODES: dict[str, tuple[int, str, str]] = {
    # Authentication
    "AUTH_REQUIRED": (401, "Sign-in required.", "info"),
    "AUTH_INVALID_CREDENTIALS": (401, "Incorrect email or password.", "warning"),
    "AUTH_ACCOUNT_DISABLED": (403, "This account has been disabled.", "warning"),
    "AUTH_ACCOUNT_LOCKED": (429, "Too many failed sign-in attempts; the account is temporarily locked.", "warning"),
    "AUTH_EMAIL_NOT_VERIFIED": (403, "Email not verified yet; please complete email verification first.", "info"),
    "AUTH_2FA_REQUIRED": (401, "A two-factor verification code is required.", "info"),
    "AUTH_2FA_INVALID": (401, "Invalid two-factor verification code.", "warning"),
    "AUTH_PASSWORD_WEAK": (400, "Password does not meet the policy requirements.", "info"),
    "AUTH_PASSWORD_REUSED": (400, "The new password cannot be the same as the current one.", "info"),
    "AUTH_EMAIL_TAKEN": (409, "This email is already registered.", "info"),
    "AUTH_TOKEN_INVALID": (400, "The link is invalid or has expired.", "info"),
    # Permissions
    "PERM_DENIED": (403, "You do not have permission to perform this action.", "warning"),
    # Rate limiting
    "RATE_LIMIT_EXCEEDED": (429, "Too many requests; please try again later.", "warning"),
    "RATE_LIMIT_LOGIN_BLOCKED": (429, "Too many sign-in attempts; please try again later.", "warning"),
    # Resources
    "RESOURCE_NOT_FOUND": (404, "The resource does not exist.", "info"),
    "RESOURCE_CONFLICT": (409, "Resource conflict.", "info"),
    # Validation
    "VALIDATION_FAILED": (400, "Request parameter validation failed.", "info"),
    # System
    "SYSTEM_NOT_IMPLEMENTED": (501, "This capability is not implemented yet.", "info"),
    "SYSTEM_UNAVAILABLE": (503, "This capability is temporarily unavailable.", "info"),
    # License (aligned with the License gate envelope)
    "LICENSE_REQUIRED": (403, "A license activation is required.", "info"),
}


class BizError(Exception):
    """The only user-facing exception business code is allowed to raise (HARD RULE: no bare strings / stack-trace leakage)."""

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
