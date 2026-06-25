"""License runtime state — fail-closed multi-point signature verification (licensing.md).

Activation credentials are written by the admin backend to `licenses/active.forge` (JSON envelope:
`{"method": "offline"|"online", "credential": "<blob or short code>"}`; also accepts a bare offline blob).
This service only reads that file: verify once on startup + re-verify every TERRANE_LICENSE_RECHECK_SECONDS
(expiry / CRL revocation / clock rollback / online lease renewal); any exception transitions to the locked state.
"""

from __future__ import annotations

import asyncio
import json
import threading
import os
import time
from pathlib import Path

import structlog
from forge_verifier import ForgeVerifier, Verdict, verify_offline
from forge_verifier._token import parse_and_verify

from app.core.config import Settings

log = structlog.get_logger("terrane.license")

METHOD_OFFLINE = "offline"
METHOD_ONLINE = "online"
_NOT_ACTIVATED = Verdict("locked", "not_activated")
_BYPASS = Verdict("active", "license_not_required")  # synthetic unlock verdict when gating is disabled (open-source edition)


def read_envelope(path: Path) -> tuple[str, str] | None:
    """Read the activation envelope, returning (method, credential); returns None if the file is missing/unparseable (= not activated)."""
    try:
        raw = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw:
        return None
    try:
        data = json.loads(raw)
        method, credential = data.get("method", ""), data.get("credential", "")
        if method in (METHOD_OFFLINE, METHOD_ONLINE) and credential:
            return method, credential
        return None
    except ValueError:
        return METHOD_OFFLINE, raw  # accept a bare .forge blob dropped in directly


class LicenseState:
    """Single-instance License state machine. verdict reads are atomic (attribute replacement); writes happen only within this class."""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # install_id is co-located with the activation envelope on the licenses/ shared volume: the three components share the same install_id = the same deployment identity,
        # stable across container restarts/database migrations (design 02 §anti-clone).
        _iid = os.path.join(os.path.dirname(settings.terrane_license_path) or ".", "install_id")
        self._verifier = ForgeVerifier(edge_url=settings.terrane_forge_edge_url or None,
                                       install_id_path=_iid)
        self._verdict: Verdict = _NOT_ACTIVATED
        self._recheck_task: asyncio.Task | None = None
        self._last_verify_mono = 0.0
        self._activated_code: str | None = None
        self._verify_lock = threading.Lock()  # serialize verification: prevent concurrent re-entrant hits to edge (avoid rate limiting)
        self.initial_checked = False  # readyz readiness signal: the first verification has completed

    @property
    def required(self) -> bool:
        """Whether gating is enabled (open-source edition defaults to False → always pass through)."""
        return self._settings.license_required

    @property
    def fingerprint(self) -> str:
        return self._verifier.fingerprint

    @property
    def verdict(self) -> Verdict:
        if not self._settings.license_required:
            return _BYPASS
        return self._verdict

    @property
    def unlocked(self) -> bool:
        if not self._settings.license_required:
            return True
        return self._verdict.unlocked

    def _load_crl(self) -> tuple[set[str], int | None, str | None]:
        """Read and verify the CRL file; untrusted/missing → empty set (the License's own validity period still provides a fallback)."""
        path = Path(self._settings.terrane_license_crl_path)
        try:
            blob = path.read_text(encoding="utf-8").strip()
        except OSError:
            return set(), None, None
        if not blob:
            return set(), None, None
        revoked = self._verifier.revoked_from_crl(blob)
        try:
            valid, payload = parse_and_verify(blob, self._verifier.master_pub)
            if valid and payload.get("kind") == "crl":
                return revoked, payload.get("crl_version"), payload.get("generated_at")
        except Exception:  # noqa: BLE001 — a CRL exception is not fatal, the License validity period still provides a fallback
            pass
        return revoked, None, None

    def verify_now(self) -> Verdict:
        """Synchronously run one full verification and update state; any exception → locked (fail-closed). The serial lock prevents concurrent re-entrant hits to edge."""
        with self._verify_lock:
            return self._verify_now_locked()

    def _verify_now_locked(self) -> Verdict:
        envelope = read_envelope(Path(self._settings.terrane_license_path))
        if envelope is None:
            verdict = _NOT_ACTIVATED
        else:
            method, credential = envelope
            try:
                verdict = self._verify(method, credential)
            except Exception:  # noqa: BLE001 — internal verification details are not leaked (zero-leakage requirement)
                log.error("license.verify_error")
                verdict = Verdict("locked", "verify_error")
        changed = verdict.status != self._verdict.status
        self._verdict = verdict
        self._last_verify_mono = time.monotonic()
        if changed:
            log.info("license.status_changed", status=verdict.status, reason=verdict.reason)
        return verdict

    def verify_if_stale(self, max_age_seconds: float) -> None:
        """Re-verify on demand, but throttled: only really verify if more than max_age_seconds has elapsed since the last verification, otherwise use the cache.
        Used by the status endpoint so that revocation/deletion is reflected near-instantly even in the active state, while limiting how often online mode hits edge."""
        if not self._settings.license_required:
            return  # gating disabled: no verification
        with self._verify_lock:
            if time.monotonic() - self._last_verify_mono >= max_age_seconds:
                self._verify_now_locked()

    def try_credential(self, method: str, credential: str) -> Verdict:
        """Verify a candidate credential (without persisting or changing the current verdict) — the pre-check for activation."""
        try:
            return self._verify(method, credential)
        except Exception:  # noqa: BLE001 — fail-closed, details not leaked
            log.error("license.try_credential_error")
            return Verdict("locked", "verify_error")

    def _verify(self, method: str, credential: str) -> Verdict:
        if method == METHOD_ONLINE:
            if self._verifier.online is None:
                return Verdict("locked", "edge_url_not_configured")
            # Same online code and an existing lease → renew (passes during the signature grace period while offline);
            # a new code (e.g. re-issued after the old ticket was revoked) → must re-activate, never renew the old ticket with the old token.
            same_code = credential == self._activated_code
            if same_code and self._verifier.online._validation_token:  # noqa: SLF001
                return self._verifier.revalidate()
            verdict = self._verifier.activate_online(credential)
            if verdict.unlocked:
                self._activated_code = credential
            return verdict
        revoked, crl_version, crl_generated_at = self._load_crl()
        return verify_offline(
            credential,
            self._verifier.master_pub,
            self._verifier.fingerprint,
            revoked_license_ids=revoked,
            state_path=self._settings.terrane_license_state_path or None,
            crl_version=crl_version,
            crl_generated_at=crl_generated_at,
            max_crl_age_days=self._settings.terrane_license_crl_max_age_days or None,
        )

    async def start(self) -> None:
        if not self._settings.license_required:
            self.initial_checked = True
            log.info("license.disabled")  # open-source edition gating disabled: no verification, no recheck loop started
            return
        await asyncio.to_thread(self.verify_now)
        self.initial_checked = True
        log.info("license.initial", status=self._verdict.status,
                 reason=self._verdict.reason, fingerprint=self.fingerprint)
        self._recheck_task = asyncio.create_task(self._recheck_loop(), name="license-recheck")

    async def stop(self) -> None:
        if self._recheck_task:
            self._recheck_task.cancel()
            try:
                await self._recheck_task
            except asyncio.CancelledError:
                pass

    async def _recheck_loop(self) -> None:
        interval = max(self._settings.terrane_license_recheck_seconds, 10)
        while True:
            await asyncio.sleep(interval)
            await asyncio.to_thread(self.verify_now)
