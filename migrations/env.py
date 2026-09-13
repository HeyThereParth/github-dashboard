"""Alembic migration environment.

Wired to the application's declarative ``Base`` metadata and ``DATABASE_URL``
so migrations are generated against the same models the app uses. No business
migrations exist yet.
"""

from alembic import context
from app import models  # noqa: F401  (register models on Base.metadata)
from app.core.config import settings
from app.core.database import Base
from sqlalchemy import create_engine, pool

config = context.config
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode (emit SQL without a DB connection)."""
    context.configure(
        url=settings.database_url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode (against a live database)."""
    connectable = create_engine(settings.database_url, poolclass=pool.NullPool)

    with connectable.connect() as connection:
        context.configure(connection=connection, target_metadata=target_metadata)

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
