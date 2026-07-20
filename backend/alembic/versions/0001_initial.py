"""initial schema - 13 tables baseline

Revision ID: 0001
Revises:
Create Date: 2026-07-20

基线迁移：创建当前所有 13 张表。后续 schema 变更走 alembic revision --autogenerate。

已有数据库的迁移策略：
- 新数据库：直接 `alembic upgrade head`
- 已有数据库（从 create_all 创建）：先 `alembic stamp head` 标记为已迁移，后续走 revision
"""
from typing import Sequence, Union

from alembic import op


# revision identifiers
revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    """创建所有表（IF NOT EXISTS 语义）

    直接复用 Base.metadata.create_all()，避免重复维护 DDL。
    op.get_bind() 返回同步连接，create_all 可直接使用。
    """
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from db.database import Base
    from db import models  # noqa: F401 — 触发所有 model 注册到 Base.metadata

    bind = op.get_bind()

    # PostgreSQL 特有：先创建枚举类型（IF NOT EXISTS）
    if bind.dialect.name == "postgresql":
        from sqlalchemy import text
        enum_values = [
            "GRID", "SMA_CROSS", "ML_SIGNAL", "CUSTOM",
            "MA_CROSS", "RSI", "BOLLINGER", "AI_GENERATED",
        ]
        # 如果枚举不存在则创建
        bind.execute(text("DO $$ BEGIN CREATE TYPE strategytype AS ENUM (); EXCEPTION WHEN duplicate_object THEN NULL; END $$"))
        for v in enum_values:
            # 安全地添加枚举值（IF NOT EXISTS 语义）
            bind.execute(text(
                f"DO $$ BEGIN ALTER TYPE strategytype ADD VALUE IF NOT EXISTS '{v}'; END $$"
            ))

    # 创建所有表（IF NOT EXISTS 语义由 create_all 内置）
    Base.metadata.create_all(bind, checkfirst=True)


def downgrade() -> None:
    """删除所有表（保留枚举类型，需要时手动 DROP）"""
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent.parent))

    from db.database import Base
    from db import models  # noqa: F401

    bind = op.get_bind()
    Base.metadata.drop_all(bind, checkfirst=True)

    # PostgreSQL：删除枚举类型
    if bind.dialect.name == "postgresql":
        from sqlalchemy import text
        bind.execute(text("DROP TYPE IF EXISTS strategytype CASCADE"))
