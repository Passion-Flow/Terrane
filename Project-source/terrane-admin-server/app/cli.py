"""terrane-admin CLI — 管理命令（bootstrap 超管 + alembic migrate）。

所有命令走与 API 相同的服务/仓储（不绕过 DB），幂等。
用法：python -m app.cli migrate up / python -m app.cli bootstrap
"""

from __future__ import annotations

import asyncio

import typer

app = typer.Typer(name="terrane-admin", help="Terrane 后台管理 CLI", no_args_is_help=True)
migrate_app = typer.Typer(help="数据库迁移")
app.add_typer(migrate_app, name="migrate")

# 出厂默认超管（authentication.md：默认超管 email = <slug>@navtra.ai；密码=邮箱）
SUPER_ADMIN_EMAIL = "terrane@navtra.ai"
SUPER_ADMIN_USERNAME = "Admin"


def _alembic_config():
    from alembic.config import Config
    return Config("alembic.ini")


@migrate_app.command("up")
def migrate_up() -> None:
    """应用所有待执行迁移（alembic upgrade head）。"""
    from alembic import command
    command.upgrade(_alembic_config(), "head")
    typer.echo("✓ migrations applied")


@migrate_app.command("down")
def migrate_down(steps: int = typer.Option(1, help="回滚的版本数")) -> None:
    from alembic import command
    command.downgrade(_alembic_config(), f"-{steps}")
    typer.echo(f"✓ rolled back {steps} revision(s)")


@app.command()
def bootstrap(silent: bool = typer.Option(False, "--silent")) -> None:
    """幂等建默认超管（terrane@navtra.ai / Admin / super_admin / 密码=邮箱）。"""
    created = asyncio.run(_bootstrap())
    if not silent:
        typer.echo("✓ super-admin created" if created
                   else "• super-admin already exists — no-op")


async def _bootstrap() -> bool:
    from app.core import security
    from app.db.session import get_sessionmaker
    from app.models.user import User
    from app.repositories.user import UserRepository

    async with get_sessionmaker()() as db:
        repo = UserRepository(db)
        if await repo.get_by_email(SUPER_ADMIN_EMAIL, include_deleted=True):
            return False
        user = User(
            email=SUPER_ADMIN_EMAIL, username=SUPER_ADMIN_USERNAME, role="super_admin",
            is_active=True,
            password_hash=security.hash_password(SUPER_ADMIN_EMAIL),  # 出厂：密码=邮箱
            must_change_password=True,  # 首登强制改密（初始化向导超管步）
        )
        db.add(user)
        await db.commit()
        return True


if __name__ == "__main__":
    app()
