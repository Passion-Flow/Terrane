"""Forge Verifier SDK (Python) — embed in a consumer product to verify Forge licenses.

    from forge_verifier import ForgeVerifier
    fv = ForgeVerifier(edge_url="https://forge.navtra.ai")
    print("Deployment ID:", fv.fingerprint)          # show on the activation page
    v = fv.verify_offline(pasted_blob)                # offline .forge
    v = fv.activate_online(pasted_code)               # online short code
    if not v.unlocked:
        show(v.message("zh-CN"))                      # 需要激活许可证.
"""

from __future__ import annotations

import os

from forge_verifier import keys
from forge_verifier.fingerprint import (
    collect_signals,
    deployment_fingerprint,
    deployment_uid,
    ensure_install_id,
)
from forge_verifier.online import OnlineClient
from forge_verifier.verifier import Verdict, verify_offline

__all__ = ["ForgeVerifier", "Verdict", "verify_offline", "OnlineClient", "deployment_fingerprint"]

_DEFAULT_INSTALL_ID_PATH = os.path.join(
    os.path.expanduser("~"), ".config", "forge", "install_id"
)


class ForgeVerifier:
    def __init__(self, edge_url: str | None = None, *, install_id_path: str | None = None) -> None:
        self.master_pub = keys.master_public_pem()
        self.edge_pub = keys.edge_lease_public_pem()
        self.fingerprint = deployment_fingerprint()
        # 反克隆身份（design 07）：注入 UID（容器/集群权威）、多信号向量、首激活随机 install_id。
        # 回退：无注入 UID 时用部署指纹当 deployment_uid——同机多组件（server/admin/gateway）
        # 共享同一指纹 → edge 按 UID 去重为「一个部署一个席位」，消除多组件抢席位的 binding_mismatch
        # 横跳。指纹来自硬件不可注入，故反克隆/防伪不削弱（克隆机指纹不同→UID 不同→照样被拒）。
        self.deployment_uid = deployment_uid() or self.fingerprint
        self.signals = collect_signals()
        self.install_id = ensure_install_id(install_id_path or _DEFAULT_INSTALL_ID_PATH)
        self.online = OnlineClient(edge_url, self.edge_pub) if edge_url else None

    def verify_offline(self, blob: str, revoked_license_ids: set[str] | None = None) -> Verdict:
        return verify_offline(blob, self.master_pub, self.fingerprint,
                              revoked_license_ids=revoked_license_ids)

    def revoked_from_crl(self, crl_blob: str) -> set[str]:
        """Verify a signed CRL with the embedded master key; return the revoked license_ids.
        An untrusted/invalid CRL is ignored (empty set) — license expiry still guards."""
        from forge_verifier._token import parse_and_verify
        try:
            valid, payload = parse_and_verify(crl_blob, self.master_pub)
        except Exception:
            return set()
        if not valid or payload.get("kind") != "crl":
            return set()
        return set(payload.get("revoked", []))

    def activate_online(self, online_code: str, cluster_id: str | None = None) -> Verdict:
        if not self.online:
            raise RuntimeError("edge_url not configured")
        return self.online.activate(
            online_code, self.fingerprint, cluster_id,
            install_id=self.install_id, signals=self.signals, deployment_uid=self.deployment_uid,
        )

    def revalidate(self) -> Verdict:
        if not self.online:
            raise RuntimeError("edge_url not configured")
        return self.online.revalidate(self.fingerprint, install_id=self.install_id)
