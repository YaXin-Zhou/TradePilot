"""initial schema - 13 tables baseline

Revision ID: 0001
Revises:
Create Date: 2026-07-20

Baseline migration: create all 13 tables. Future schema changes go through
`alembic revision --autogenerate`.

Migration strategy for existing databases:
- new database: run `alembic upgrade head` directly
- existing database (created via create_all): first `alembic stamp head`, then use revision
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """Create all tables (IF NOT EXISTS semantics).

    Reuses Base.metadata.create_all() to avoid duplicating DDL.
    op.get_bind() returns a sync connection that create_all can use directly.
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from db.database import Base
    from db import models  # noqa: F401 — register all models on Base.metadata

    bind = op.get_bind()

    # PostgreSQL-specific: create enum type first (IF NOT EXISTS)
    if bind.dialect.name == "postgresql":
        from sqlalchemy import text
        enum_values = [
            "GRID", "SMA_CROSS", "ML_SIGNAL", "CUSTOM",
            "MA_CROSS", "RSI", "BOLLINGER", "AI_GENERATED",
        ]
        # create the enum if it does not exist
        bind.execute(text("DO $$ BEGIN CREATE TYPE strategytype AS ENUM (); EXCEPTION WHEN duplicate_object THEN NULL; END $$"))
        for v in enum_values:
            # safely add enum values (IF NOT EXISTS semantics)
            bind.execute(text(
                f"DO $$ BEGIN ALTER TYPE strategytype ADD VALUE IF NOT EXISTS '{v}'; END $$"
            ))

    # create all tables (IF NOT EXISTS via checkfirst)
    Base.metadata.create_all(bind, checkfirst=True)


def downgrade() -> None:
    """Drop all tables (keep enum type, drop manually if needed)."""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from db.database import Base
    from db import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind, checkfirst=True)

    # PostgreSQL: drop enum type
    if bind.dialect.name == "postgresql":
        from sqlalchemy import text
        bind.execute(text("DROP TYPE IF EXISTS strategytype CASCADE"))
