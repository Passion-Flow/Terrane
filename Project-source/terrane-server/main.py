"""本地开发入口：python main.py（02-Backend/tech-stack.md 启动约定）。"""

from __future__ import annotations

import uvicorn

from app.core.config import get_settings


def main() -> None:
    settings = get_settings()
    uvicorn.run(
        "app.main:app",
        host=settings.terrane_host,
        port=settings.terrane_port,
        log_level=settings.terrane_log_level.lower(),
    )


if __name__ == "__main__":
    main()
