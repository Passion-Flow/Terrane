"""Verifier — the embeddable license check. fail-closed: any anomaly => locked.

Lock-state copy is fixed by the global rule (licensing.md / i18n.md): the product renders
`需要激活许可证.` / `License activation required.` when a Verdict is not active.
"""

from __future__ import annotations

import datetime
import json
import os
from dataclasses import dataclass, field

from forge_verifier import _token

LOCK_MESSAGE = {"zh-CN": "需要激活许可证.", "en": "License activation required."}

# Verdict statuses
ACTIVE, EXPIRING, EXPIRED, REVOKED = "active", "expiring", "expired", "revoked"
BINDING_MISMATCH, INVALID_SIGNATURE, LOCKED = "binding_mismatch", "invalid_signature", "locked"
_UNLOCKED = {ACTIVE, EXPIRING}


@dataclass
class Verdict:
    status: str
    reason: str = ""
    payload: dict = field(default_factory=dict)

    @property
    def unlocked(self) -> bool:
        return self.status in _UNLOCKED

    def message(self, lang: str = "zh-CN") -> str:
        # Any non-active verdict shows the locked activation prompt to end users.
        return "" if self.unlocked else LOCK_MESSAGE.get(lang, LOCK_MESSAGE["en"])


def _now() -> datetime.datetime:
    return datetime.datetime.now(datetime.timezone.utc)


def _parse_dt(value: str | None) -> datetime.datetime | None:
    if not value:
        return None
    return datetime.datetime.fromisoformat(value.replace("Z", "+00:00"))


def _load_state(path: str) -> dict:
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _save_state(path: str, state: dict) -> None:
    # best-effort: a read-only FS can't be hardened, but never crash the product over it.
    try:
        d = os.path.dirname(path)
        if d:
            os.makedirs(d, exist_ok=True)
        tmp = path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(state, f)
        os.replace(tmp, path)
    except Exception:
        pass


def verify_offline(
    blob: str, master_public_pem: bytes, local_fingerprint: str, *,
    revoked_license_ids: set[str] | None = None, now: datetime.datetime | None = None,
    state_path: str | None = None, crl_version: int | None = None,
    crl_generated_at: str | None = None, max_crl_age_days: int | None = None,
    clock_skew_minutes: int = 10,
) -> Verdict:
    """Verify an offline `.forge` token fully offline (signature + expiry + binding + CRL).

    Anti-crack hardening (enabled when `state_path` is given — a writable file the SDK owns):
      * clock-rollback: a monotonic watermark of the highest time/CRL date ever seen; if the system
        clock is wound back below it (beyond `clock_skew_minutes`), the verdict is LOCKED.
      * CRL anti-rollback: pass the consulted CRL's `crl_version`; an older (replayed) signed CRL is
        rejected (LOCKED).
      * CRL freshness: with `max_crl_age_days`, a starved/too-old CRL (`crl_generated_at`) is LOCKED.
    These are best-effort mitigations for an attacker-controlled offline host; document accordingly.
    """
    now = now or _now()
    try:
        valid, payload = _token.parse_and_verify(blob, master_public_pem)
    except Exception:
        return Verdict(LOCKED, "malformed")
    if not valid:
        return Verdict(INVALID_SIGNATURE, "signature")            # tampered / wrong key

    # --- anti-rollback hardening (state-backed) ---
    state = _load_state(state_path) if state_path else None
    if state is not None:
        wm = _parse_dt(state.get("time_watermark"))
        if wm is not None and now < wm - datetime.timedelta(minutes=clock_skew_minutes):
            return Verdict(LOCKED, "clock_rollback", payload)     # system clock wound back
        if crl_version is not None and state.get("crl_version") is not None \
                and crl_version < state["crl_version"]:
            return Verdict(LOCKED, "crl_rollback", payload)       # stale signed CRL replayed
        if max_crl_age_days is not None and crl_generated_at:
            gen = _parse_dt(crl_generated_at)
            if gen is not None and (now - gen).days > max_crl_age_days:
                return Verdict(LOCKED, "crl_stale", payload)      # CRL starved / too old
        # advance the watermark (highest of: prior watermark, now, this CRL's generated_at) + persist
        new_wm = now
        for cand in (wm, _parse_dt(crl_generated_at)):
            if cand is not None and cand > new_wm:
                new_wm = cand
        state["time_watermark"] = new_wm.isoformat()
        if crl_version is not None:
            state["crl_version"] = max(crl_version, state.get("crl_version", crl_version))
        if crl_generated_at:
            state["crl_generated_at"] = crl_generated_at
        _save_state(state_path, state)

    if payload.get("binding", "hard") == "hard":
        if payload.get("bound_fingerprint") != local_fingerprint:  # copied / migrated host
            return Verdict(BINDING_MISMATCH, "fingerprint", payload)
    if revoked_license_ids and payload.get("license_id") in revoked_license_ids:
        return Verdict(REVOKED, "crl", payload)
    until = _parse_dt(payload.get("active_until"))
    if until is not None:
        if now >= until:
            return Verdict(EXPIRED, "expired", payload)
        if (until - now).days <= 30:
            return Verdict(EXPIRING, "expiring", payload)
    return Verdict(ACTIVE, "ok", payload)
