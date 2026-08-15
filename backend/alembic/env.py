"""Alembic environment config (N4)

Supports async SQLAlchemy engine: converts `postgresql+asyncpg://` to `postgresql://` (sync driver).
"""
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# add backend dir to sys.path so alembic can import project modules
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings  # noqa: E402
from db.database import Base  # noqa: E402
# import all models so Base.metadata knows all tables
from db import models  # noqa: F401, E402

# alembic config
config = context.config

# logging config
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# target metadata — used by autogenerate
target_metadata = Base.metadata

# read DATABASE_URL from settings and convert to sync URL
def _get_sync_url() -> str:
    """Convert asyncpg URL to sync URL for alembic."""
    url = settings.DATABASE_URL
    # postgresql+asyncpg://user:pass@host:port/db -> postgresql://user:pass@host:port/db
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    # sqlite+aiosqlite:// -> sqlite://
    url = url.replace("sqlite+aiosqlite://", "sqlite://")
    return url


# set sqlalchemy.url
config.set_main_option("sqlalchemy.url", _get_sync_url())


def run_migrations_offline() -> None:
    """Offline mode: generate SQL script without connecting to DB."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Online mode: connect to DB and run migrations."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
