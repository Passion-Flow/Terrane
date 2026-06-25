"""terrane-admin CLI — management commands (bootstrap super-admin + alembic migrate).

All commands go through the same services/repositories as the API (no DB bypass) and are idempotent.
Usage: python -m app.cli migrate up / python -m app.cli bootstrap
"""

from __future__ import annotations

import asyncio

import typer

app = typer.Typer(name="terrane-admin", help="Terrane admin management CLI", no_args_is_help=True)
migrate_app = typer.Typer(help="Database migrations")
app.add_typer(migrate_app, name="migrate")

# Factory default super-admin (authentication.md: default super-admin email = <slug>@navtra.ai; password = email)
SUPER_ADMIN_EMAIL = "terrane@navtra.ai"
SUPER_ADMIN_USERNAME = "Admin"


def _alembic_config():
    from alembic.config import Config
    return Config("alembic.ini")


@migrate_app.command("up")
def migrate_up() -> None:
    """Apply all pending migrations (alembic upgrade head)."""
    from alembic import command
    command.upgrade(_alembic_config(), "head")
    typer.echo("✓ migrations applied")


@migrate_app.command("down")
def migrate_down(steps: int = typer.Option(1, help="Number of revisions to roll back")) -> None:
    from alembic import command
    command.downgrade(_alembic_config(), f"-{steps}")
    typer.echo(f"✓ rolled back {steps} revision(s)")


@app.command()
def bootstrap(silent: bool = typer.Option(False, "--silent")) -> None:
    """Idempotently create the default super-admin (terrane@navtra.ai / Admin / super_admin / password = email)."""
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
            password_hash=security.hash_password(SUPER_ADMIN_EMAIL),  # factory: password = email
            must_change_password=True,  # force password change on first login (setup wizard super-admin step)
        )
        db.add(user)
        await db.commit()
        return True


if __name__ == "__main__":
    app()
