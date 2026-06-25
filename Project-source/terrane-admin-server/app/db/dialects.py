"""Xinchuang (domestic) DB compatibility matrix — DATABASE_TYPE → SQLAlchemy dialect + async driver mapping.

The control plane ORM/migrations are developed on postgres but must be switchable to domestic databases. This module is the **only**
type→(dialect+driver+connect_args) resolution point; both session.py and platform.py reuse it,
without changing the default postgres behavior (DATABASE_TYPE defaults to postgres → postgresql+asyncpg, identical to the original).

Compatibility groups (see docs/xinchuang-db-matrix.md):
  - PG protocol family (postgresql+asyncpg reused directly): postgres / opengauss / polardb-pg /
    gaussdb / kingbase. opengauss/gaussdb/kingbase/polardb-pg have wire protocols highly compatible
    with PostgreSQL and can be connected directly with asyncpg; a few DBs require enabling PG
    compatibility mode / setting the password encryption algorithm on the server (see "Known limitations" in the docs).
  - MySQL protocol family (mysql+asyncmy async driver): mysql / oceanbase / tidb / polardb-x.
  - Dameng DM8 (dameng): third-party SQLAlchemy dialect sqlalchemy-dm, no official async driver →
    degrades to a synchronous dialect URL (requires a greenlet bridge; under this control plane's async stack Dameng is "experimental/limited" tier).
  - oracle: oracle+oracledb (python-oracledb thin mode, supports asyncio).

**Drivers are on-demand optional dependencies** (pyproject extras: xinchuang-pg / xinchuang-mysql /
xinchuang-dameng / xinchuang-oracle). A missing driver raises a clear ImportError instead of crashing default behavior.
"""

from __future__ import annotations

from dataclasses import dataclass

# Default database type — never changes.
DEFAULT_DATABASE_TYPE = "postgres"


@dataclass(frozen=True)
class DialectSpec:
    """The resolution result for one DATABASE_TYPE."""

    db_type: str
    drivername: str  # the "dialect+driver" part of the SQLAlchemy URL
    driver_module: str  # import name used in the error hint when missing
    extra: str  # the pyproject extra name that installs this driver
    is_async: bool  # whether the driver is natively async (False = needs a sync bridge, limited)
    note: str = ""


# DATABASE_TYPE → DialectSpec. Keys are lowercase-normalized values.
_MATRIX: dict[str, DialectSpec] = {
    # ── PG protocol family: postgresql+asyncpg reused directly ──
    "postgres": DialectSpec(
        "postgres", "postgresql+asyncpg", "asyncpg", "xinchuang-pg", True,
        "Default; native PostgreSQL.",
    ),
    "postgresql": DialectSpec(
        "postgres", "postgresql+asyncpg", "asyncpg", "xinchuang-pg", True,
        "postgres alias.",
    ),
    "opengauss": DialectSpec(
        "opengauss", "postgresql+asyncpg", "asyncpg", "xinchuang-pg", True,
        "openGauss is PG-protocol compatible, connect with asyncpg; the server needs password_encryption_type=1 "
        "(sha256) or compatibility enabled, otherwise the asyncpg SCRAM handshake may fail.",
    ),
    "polardb-pg": DialectSpec(
        "polardb-pg", "postgresql+asyncpg", "asyncpg", "xinchuang-pg", True,
        "Alibaba Cloud PolarDB for PostgreSQL, fully PG-protocol compatible, asyncpg direct connect.",
    ),
    "gaussdb": DialectSpec(
        "gaussdb", "postgresql+asyncpg", "asyncpg", "xinchuang-pg", True,
        "Huawei GaussDB (based on openGauss), PG-protocol compatible; same password-encryption caveats as opengauss.",
    ),
    "kingbase": DialectSpec(
        "kingbase", "postgresql+asyncpg", "asyncpg", "xinchuang-pg", True,
        "KingbaseES, usable with asyncpg in PG compatibility mode (database_mode=pg); "
        "Oracle compatibility mode is out of scope for this matrix.",
    ),
    # ── MySQL protocol family: mysql+asyncmy async driver ──
    "mysql": DialectSpec(
        "mysql", "mysql+asyncmy", "asyncmy", "xinchuang-mysql", True,
        "MySQL 8.x; asyncmy native async driver.",
    ),
    "oceanbase": DialectSpec(
        "oceanbase", "mysql+asyncmy", "asyncmy", "xinchuang-mysql", True,
        "OceanBase (MySQL mode), connect via the MySQL protocol; an ob mysql tenant is recommended.",
    ),
    "tidb": DialectSpec(
        "tidb", "mysql+asyncmy", "asyncmy", "xinchuang-mysql", True,
        "TiDB is MySQL-protocol compatible, asyncmy direct connect.",
    ),
    "polardb-x": DialectSpec(
        "polardb-x", "mysql+asyncmy", "asyncmy", "xinchuang-mysql", True,
        "Alibaba Cloud PolarDB-X (distributed MySQL), connect via the MySQL protocol.",
    ),
    # ── Dameng DM8: sqlalchemy-dm third-party dialect, no official async driver → sync bridge, limited ──
    "dameng": DialectSpec(
        "dameng", "dm+dmPython", "dmPython", "xinchuang-dameng", False,
        "Dameng DM8; sqlalchemy-dm dialect + dmPython sync driver, runs through a greenlet "
        "bridge under the async stack, with limited concurrency, classed as experimental/limited tier (see docs).",
    ),
    "dm8": DialectSpec(
        "dameng", "dm+dmPython", "dmPython", "xinchuang-dameng", False,
        "dameng alias.",
    ),
    # ── Oracle: python-oracledb (supports asyncio) ──
    "oracle": DialectSpec(
        "oracle", "oracle+oracledb", "oracledb", "xinchuang-oracle", True,
        "Oracle; python-oracledb thin mode supports asyncio.",
    ),
}


def normalize_type(db_type: str | None) -> str:
    return (db_type or DEFAULT_DATABASE_TYPE).strip().lower()


def resolve_dialect(db_type: str | None) -> DialectSpec:
    """DATABASE_TYPE → DialectSpec; raises a clear error for unknown types."""
    key = normalize_type(db_type)
    spec = _MATRIX.get(key)
    if spec is None:
        supported = ", ".join(sorted({s.db_type for s in _MATRIX.values()}))
        raise ValueError(
            f"Unknown DATABASE_TYPE={db_type!r}; supported: {supported}. "
            f"(postgres is the default)"
        )
    return spec


def ensure_driver(spec: DialectSpec) -> None:
    """Confirm the corresponding async driver is importable; on absence, give clear guidance on "which extra to install".

    Does not force the import at the resolution stage (so unit tests/CLI that only build a URL don't have to install all drivers); only call it right
    before actually creating the engine.
    """
    import importlib.util

    if importlib.util.find_spec(spec.driver_module) is None:
        raise ImportError(
            f"DATABASE_TYPE={spec.db_type} requires driver '{spec.driver_module}', which is not installed. "
            f"Please install the optional dependency: pip install 'terrane-admin-server[{spec.extra}]'."
        )


def connect_args_for(spec: DialectSpec, *, ssl_mode: str) -> dict:
    """Return connect_args (ssl / charset) per dialect family.

    - asyncpg (PG protocol family): ssl uses bool/SSLContext, require/verify-* → enabled.
    - asyncmy (MySQL protocol family): defaults to utf8mb4; ssl via an ssl dict (require → {}=enabled).
    - dameng / oracle: no ssl injected by default (configured via the deployment-side DSN/wallet).
    """
    ssl_on = ssl_mode in ("require", "verify-ca", "verify-full")
    drivername = spec.drivername
    if drivername.startswith("postgresql+asyncpg"):
        return {"ssl": True} if ssl_on else {}
    if drivername.startswith("mysql+asyncmy"):
        args: dict = {"charset": "utf8mb4"}
        if ssl_on:
            args["ssl"] = {}  # asyncmy: a non-empty ssl enables TLS
        return args
    # dameng / oracle: connection parameters are determined by the deployment side (DSN/wallet), not injected here.
    return {}
