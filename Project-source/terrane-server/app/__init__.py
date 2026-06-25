"""Terrane user-facing business control plane (terrane-api).

Vendored third-party packages (the Forge Verifier SDK) live in app/vendor and are
imported under their original package names. The SDK uses absolute imports internally
(`from forge_verifier import …`), so the vendor directory is added to sys.path.
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR = str(Path(__file__).resolve().parent / "vendor")
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)
