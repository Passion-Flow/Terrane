"""Terrane 前台业务控制面（terrane-api）。

vendored 第三方包（Forge Verifier SDK）置于 app/vendor，按原包名 import：
SDK 内部使用绝对导入（`from forge_verifier import …`），因此把 vendor 目录加入 sys.path。
"""

from __future__ import annotations

import sys
from pathlib import Path

_VENDOR = str(Path(__file__).resolve().parent / "vendor")
if _VENDOR not in sys.path:
    sys.path.insert(0, _VENDOR)
