"""信创 DB 适配矩阵 — DATABASE_TYPE → SQLAlchemy 方言 + async 驱动映射。

控制面 ORM/迁移在 postgres 上开发，但需可切换到国产数据库。本模块是 **唯一**
的 type→(dialect+driver+connect_args) 解析点；session.py / platform.py 都复用它，
不改默认 postgres 行为（DATABASE_TYPE 缺省 = postgres → postgresql+asyncpg，与原一致）。

兼容性分组（详见 docs/xinchuang-db-matrix.md）：
  - PG 协议族（postgresql+asyncpg 直接复用）：postgres / opengauss / polardb-pg /
    gaussdb / kingbase。opengauss/gaussdb/kingbase/polardb-pg 在线协议高度兼容
    PostgreSQL，可直接用 asyncpg 连；个别 DB 需在服务端开启 PG 兼容模式 / 设置
    密码加密算法（见文档「已知限制」）。
  - MySQL 协议族（mysql+asyncmy 异步驱动）：mysql / oceanbase / tidb / polardb-x。
  - 达梦 DM8（dameng）：SQLAlchemy 第三方方言 sqlalchemy-dm，无官方 async 驱动 →
    退化为同步方言 URL（需 greenlet 桥；本控制面 async 栈下达梦为「实验/受限」档）。
  - oracle：oracle+oracledb（python-oracledb thin 模式，支持 asyncio）。

**驱动为按需可选依赖**（pyproject extras：xinchuang-pg / xinchuang-mysql /
xinchuang-dameng / xinchuang-oracle）。缺驱动时给清晰 ImportError 报错而非默认行为崩溃。
"""

from __future__ import annotations

from dataclasses import dataclass

# 默认（缺省）数据库类型 — 绝不改变。
DEFAULT_DATABASE_TYPE = "postgres"


@dataclass(frozen=True)
class DialectSpec:
    """一个 DATABASE_TYPE 的解析结果。"""

    db_type: str
    drivername: str  # SQLAlchemy URL 的 "dialect+driver"
    driver_module: str  # 缺失时报错提示用的 import 名
    extra: str  # 安装该驱动的 pyproject extra 名
    is_async: bool  # 该驱动是否原生 async（False = 需同步桥，受限）
    note: str = ""


# DATABASE_TYPE → DialectSpec。键为小写规范化值。
_MATRIX: dict[str, DialectSpec] = {
    # ── PG 协议族：postgresql+asyncpg 直接复用 ──
    "postgres": DialectSpec(
        "postgres", "postgresql+asyncpg", "asyncpg", "xinchuang-pg", True,
        "默认；原生 PostgreSQL。",
    ),
    "postgresql": DialectSpec(
        "postgres", "postgresql+asyncpg", "asyncpg", "xinchuang-pg", True,
        "postgres 别名。",
    ),
    "opengauss": DialectSpec(
        "opengauss", "postgresql+asyncpg", "asyncpg", "xinchuang-pg", True,
        "openGauss PG 协议兼容，用 asyncpg 连；服务端需 password_encryption_type=1 "
        "(sha256) 或开启兼容，否则 asyncpg SCRAM 握手可能失败。",
    ),
    "polardb-pg": DialectSpec(
        "polardb-pg", "postgresql+asyncpg", "asyncpg", "xinchuang-pg", True,
        "阿里云 PolarDB for PostgreSQL，PG 协议完全兼容，asyncpg 直连。",
    ),
    "gaussdb": DialectSpec(
        "gaussdb", "postgresql+asyncpg", "asyncpg", "xinchuang-pg", True,
        "华为 GaussDB（基于 openGauss），PG 协议兼容；与 opengauss 同密码加密注意项。",
    ),
    "kingbase": DialectSpec(
        "kingbase", "postgresql+asyncpg", "asyncpg", "xinchuang-pg", True,
        "人大金仓 KingbaseES，PG 兼容模式（database_mode=pg）下可用 asyncpg；"
        "Oracle 兼容模式不适用本矩阵。",
    ),
    # ── MySQL 协议族：mysql+asyncmy 异步驱动 ──
    "mysql": DialectSpec(
        "mysql", "mysql+asyncmy", "asyncmy", "xinchuang-mysql", True,
        "MySQL 8.x；asyncmy 原生 async 驱动。",
    ),
    "oceanbase": DialectSpec(
        "oceanbase", "mysql+asyncmy", "asyncmy", "xinchuang-mysql", True,
        "OceanBase（MySQL 模式），按 MySQL 协议连；建议 ob mysql 租户。",
    ),
    "tidb": DialectSpec(
        "tidb", "mysql+asyncmy", "asyncmy", "xinchuang-mysql", True,
        "TiDB MySQL 协议兼容，asyncmy 直连。",
    ),
    "polardb-x": DialectSpec(
        "polardb-x", "mysql+asyncmy", "asyncmy", "xinchuang-mysql", True,
        "阿里云 PolarDB-X（分布式 MySQL），按 MySQL 协议连。",
    ),
    # ── 达梦 DM8：sqlalchemy-dm 第三方方言，无官方 async 驱动 → 同步桥，受限 ──
    "dameng": DialectSpec(
        "dameng", "dm+dmPython", "dmPython", "xinchuang-dameng", False,
        "达梦 DM8；sqlalchemy-dm 方言 + dmPython 同步驱动，async 栈下经 greenlet "
        "桥运行，并发受限，列为实验/受限档（详见文档）。",
    ),
    "dm8": DialectSpec(
        "dameng", "dm+dmPython", "dmPython", "xinchuang-dameng", False,
        "dameng 别名。",
    ),
    # ── Oracle：python-oracledb（支持 asyncio）──
    "oracle": DialectSpec(
        "oracle", "oracle+oracledb", "oracledb", "xinchuang-oracle", True,
        "Oracle；python-oracledb thin 模式支持 asyncio。",
    ),
}


def normalize_type(db_type: str | None) -> str:
    return (db_type or DEFAULT_DATABASE_TYPE).strip().lower()


def resolve_dialect(db_type: str | None) -> DialectSpec:
    """DATABASE_TYPE → DialectSpec；未知类型给清晰报错。"""
    key = normalize_type(db_type)
    spec = _MATRIX.get(key)
    if spec is None:
        supported = ", ".join(sorted({s.db_type for s in _MATRIX.values()}))
        raise ValueError(
            f"未知 DATABASE_TYPE={db_type!r}；支持：{supported}。"
            f"（postgres 为默认）"
        )
    return spec


def ensure_driver(spec: DialectSpec) -> None:
    """确认对应 async 驱动可导入；缺失时给「装哪个 extra」的明确指引。

    不在解析阶段强制导入（避免仅构造 URL 的单测/CLI 必须装全驱动），仅在真正
    建 engine 前调用。
    """
    import importlib.util

    if importlib.util.find_spec(spec.driver_module) is None:
        raise ImportError(
            f"DATABASE_TYPE={spec.db_type} 需驱动 '{spec.driver_module}'，未安装。"
            f"请安装可选依赖：pip install 'terrane-admin-server[{spec.extra}]'。"
        )


def connect_args_for(spec: DialectSpec, *, ssl_mode: str) -> dict:
    """按方言族返回 connect_args（ssl / 字符集）。

    - asyncpg（PG 协议族）：ssl 用布尔/SSLContext，require/verify-* → 开启。
    - asyncmy（MySQL 协议族）：默认 utf8mb4；ssl 经 ssl 字典（require → {}=开启）。
    - dameng / oracle：默认不注 ssl（按部署侧 DSN/钱包配置）。
    """
    ssl_on = ssl_mode in ("require", "verify-ca", "verify-full")
    drivername = spec.drivername
    if drivername.startswith("postgresql+asyncpg"):
        return {"ssl": True} if ssl_on else {}
    if drivername.startswith("mysql+asyncmy"):
        args: dict = {"charset": "utf8mb4"}
        if ssl_on:
            args["ssl"] = {}  # asyncmy：非空 ssl 即启用 TLS
        return args
    # dameng / oracle：连接参数由部署侧（DSN/wallet）决定，不在此注入。
    return {}
