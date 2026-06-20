"""Hardware fingerprint & deployment identity (licensing.md / design 07-identity-anticlone).

Identity resolution (production):
  1. Injected `FORGE_DEPLOYMENT_UID` — honored ONLY inside a container/K8s (hardware binding
     is impossible there; the customer pins a stable uid via ConfigMap/Secret, server-side
     seat/dedup enforces anti-abuse). On bare metal an injected uid is ignored so a copier
     cannot spoof the bound id by setting an env var.
  2. Multi-signal hardware fingerprint — DMI product_uuid / board / disk serial / cpu /
     machine-id / MAC; fuzzy-matched server-side so a swapped disk/NIC does not lock out.
  3. install_id — a first-activation random id, persisted locally (0600), double-locked with
     the fingerprint server-side: it gives "reinstall = new identity" while the fingerprint
     keeps it pinned to this host (a copied install_id fails on a different machine).

`deployment_fingerprint()` keeps its original single-machine-id value for backward
compatibility (already-bound licenses must keep matching); `collect_signals()` and
`ensure_install_id()` are additive and sent alongside it.
"""

from __future__ import annotations

import hashlib
import os
import platform
import subprocess
import uuid

# Dev-only override (unchanged): lets tests pin a fingerprint without real hardware.
_DEV_ENV = "FORGE_SDK_DEV"
_UID_ENV = "FORGE_DEPLOYMENT_UID"


def _in_container() -> bool:
    """Best-effort container/K8s detection — only then is an injected uid authoritative."""
    if os.environ.get("KUBERNETES_SERVICE_HOST"):
        return True
    if os.path.exists("/.dockerenv"):
        return True
    try:
        with open("/proc/1/cgroup", encoding="utf-8") as fh:
            blob = fh.read()
            if "docker" in blob or "kubepods" in blob or "containerd" in blob:
                return True
    except OSError:
        pass
    return False


def deployment_uid() -> str | None:
    """Injected stable uid, authoritative ONLY in dev or inside a container/K8s."""
    uid = os.environ.get(_UID_ENV)
    if not uid:
        return None
    if os.environ.get(_DEV_ENV) or _in_container():
        return uid
    return None  # bare metal: ignore injection (anti-spoof)


def _read_first(*paths: str) -> str | None:
    for path in paths:
        try:
            if os.path.isfile(path):
                with open(path, encoding="utf-8") as fh:
                    if v := fh.read().strip():
                        return v
        except OSError:
            continue
    return None


def _machine_id() -> str | None:
    system = platform.system()
    try:
        if system == "Linux":
            return _read_first("/etc/machine-id", "/var/lib/dbus/machine-id")
        if system == "Darwin":
            out = subprocess.check_output(
                ["ioreg", "-rd1", "-c", "IOPlatformExpertDevice"], text=True, timeout=5
            )
            for line in out.splitlines():
                if "IOPlatformUUID" in line:
                    return line.split("=")[-1].strip().strip('"')
        elif system == "Windows":
            import winreg  # type: ignore

            key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Cryptography")
            value, _ = winreg.QueryValueEx(key, "MachineGuid")
            return value
    except Exception:
        return None
    return None


def _dmi(field: str) -> str | None:
    # Linux DMI/SMBIOS: stronger than machine-id, what cloud providers use as instance id.
    return _read_first(f"/sys/class/dmi/id/{field}")


def _cpu_sig() -> str | None:
    try:
        info = f"{platform.machine()}|{platform.processor()}|{os.cpu_count()}"
        return info if info.strip("|") else None
    except Exception:
        return None


def _mac() -> str | None:
    node = uuid.getnode()
    # getnode() sets the multicast bit when it had to invent a random MAC → unreliable, skip.
    if (node >> 40) & 0x1:
        return None
    return f"{node:012x}"


def _raw_machine_id() -> str:
    """Original single-id raw value — prefixes preserved EXACTLY (linux:/macos:/windows:/
    fallback:/override:) so deployment_fingerprint() keeps its pre-upgrade value.

    Production containers/K8s (`uid:` branch): per-pod machine-ids are random noise, so the
    offline `.forge` binding must compare against the injected stable deployment uid —
    mirroring the online activate path where the uid is the authoritative identity. The
    activation page then shows a uid-derived 64-hex Deployment ID that is stable across pod
    restarts and shared by every replica (one cluster = one uid = one license). Bare metal
    still ignores the env var (anti-spoof); the dev `override:` branch keeps its historic
    derivation so already-bound dev licenses stay valid."""
    if os.environ.get(_DEV_ENV):
        override = os.environ.get(_UID_ENV)
        if override:
            return f"override:{override}"
    injected = os.environ.get(_UID_ENV)
    if injected and _in_container():
        return f"uid:{injected}"
    system = platform.system()
    mid = _machine_id()
    if mid:
        prefix = {"Linux": "linux", "Darwin": "macos", "Windows": "windows"}.get(system, system.lower())
        return f"{prefix}:{mid}"
    return f"fallback:{platform.node()}:{uuid.getnode():012x}"


def deployment_fingerprint() -> str:
    """SHA-256 of the raw machine id — UNCHANGED value (page-displayed Deployment ID)."""
    return hashlib.sha256(_raw_machine_id().encode("utf-8")).hexdigest()


def collect_signals() -> dict[str, str]:
    """Multi-signal vector (each value hashed). Sent additively for server-side fuzzy match
    & clone detection. Missing signals are simply omitted — never fabricated."""
    raw = {
        "dmi_product_uuid": _dmi("product_uuid"),
        "board_serial": _dmi("board_serial"),
        "disk_serial": _dmi("product_serial"),
        "cpu_sig": _cpu_sig(),
        "machine_id": _machine_id(),
        "mac": _mac(),
    }
    return {
        k: hashlib.sha256(v.encode("utf-8")).hexdigest()
        for k, v in raw.items()
        if v
    }


def ensure_install_id(path: str) -> str:
    """First-activation random 128-bit install id, persisted 0600. Stable across restarts,
    regenerated only when the file is gone (reinstall / fresh deploy = new identity)."""
    try:
        existing = _read_first(path)
        if existing and len(existing) >= 16:
            return existing
    except Exception:
        pass
    install_id = uuid.uuid4().hex + uuid.uuid4().hex  # 256-bit hex
    try:
        os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(install_id)
    except OSError:
        pass  # non-persistent env (read-only fs): id lives for this process only
    return install_id
