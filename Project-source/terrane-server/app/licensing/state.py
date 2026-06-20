"""License 运行时状态 — fail-closed 多点验签（licensing.md）。

激活凭据由后台管理端写入 `licenses/active.forge`（JSON 信封：
`{"method": "offline"|"online", "credential": "<blob 或短码>"}`；兼容裸 offline blob）。
本服务只读该文件：启动验一次 + 每 TERRANE_LICENSE_RECHECK_SECONDS 复验
（过期 / CRL 吊销 / 时钟回拨 / 在线租约续期），任何异常一律转入锁定态。
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


def read_envelope(path: Path) -> tuple[str, str] | None:
    """读取激活信封，返回 (method, credential)；文件缺失/无法解析返回 None（= 未激活）。"""
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
        return METHOD_OFFLINE, raw  # 兼容直接投放的裸 .forge blob


class LicenseState:
    """单实例 License 状态机。verdict 读取是原子的（属性替换），写入仅在本类内发生。"""

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        # install_id 与激活信封同放 licenses/ 共享卷：三组件共享同一 install_id = 同一部署身份，
        # 容器重启/迁库后仍稳定（design 02 §反克隆）。
        _iid = os.path.join(os.path.dirname(settings.terrane_license_path) or ".", "install_id")
        self._verifier = ForgeVerifier(edge_url=settings.terrane_forge_edge_url or None,
                                       install_id_path=_iid)
        self._verdict: Verdict = _NOT_ACTIVATED
        self._recheck_task: asyncio.Task | None = None
        self._last_verify_mono = 0.0
        self._activated_code: str | None = None
        self._verify_lock = threading.Lock()  # 串行验签：禁并发重入打 edge（防限流）
        self.initial_checked = False  # readyz 就绪信号：首次验签已完成

    @property
    def fingerprint(self) -> str:
        return self._verifier.fingerprint

    @property
    def verdict(self) -> Verdict:
        return self._verdict

    @property
    def unlocked(self) -> bool:
        return self._verdict.unlocked

    def _load_crl(self) -> tuple[set[str], int | None, str | None]:
        """读取并验签 CRL 文件；不可信/缺失 → 空集（License 自身有效期仍兜底）。"""
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
        except Exception:  # noqa: BLE001 — CRL 异常不致命，License 有效期仍兜底
            pass
        return revoked, None, None

    def verify_now(self) -> Verdict:
        """同步执行一次完整验签并更新状态；任何异常 → 锁定（fail-closed）。串行锁防并发重入打 edge。"""
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
            except Exception:  # noqa: BLE001 — 验签内部细节不外泄（零泄露要求）
                log.error("license.verify_error")
                verdict = Verdict("locked", "verify_error")
        changed = verdict.status != self._verdict.status
        self._verdict = verdict
        self._last_verify_mono = time.monotonic()
        if changed:
            log.info("license.status_changed", status=verdict.status, reason=verdict.reason)
        return verdict

    def verify_if_stale(self, max_age_seconds: float) -> None:
        """按需重验，但节流：距上次验签超过 max_age_seconds 才真验，否则吃缓存。
        用于状态接口让吊销/删除在 active 态也能近即时反映，同时限制在线模式打 edge 的频率。"""
        with self._verify_lock:
            if time.monotonic() - self._last_verify_mono >= max_age_seconds:
                self._verify_now_locked()

    def try_credential(self, method: str, credential: str) -> Verdict:
        """验证一份候选凭据（不落盘、不改变当前 verdict）——激活的前置校验。"""
        try:
            return self._verify(method, credential)
        except Exception:  # noqa: BLE001 — fail-closed，细节不外泄
            log.error("license.try_credential_error")
            return Verdict("locked", "verify_error")

    def _verify(self, method: str, credential: str) -> Verdict:
        if method == METHOD_ONLINE:
            if self._verifier.online is None:
                return Verdict("locked", "edge_url_not_configured")
            # 同一个在线码且已持有租约 → 续期（断网在签名宽限期内放行）；
            # 换了新码（如旧票被吊销后重新签发）→ 必须重新激活，绝不拿旧 token 续旧票。
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
