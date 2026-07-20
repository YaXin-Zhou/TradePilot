"""Alembic 环境配置（N4）

支持异步 SQLAlchemy 引擎：将 `postgresql+asyncpg://` 转换为 `postgresql://`（psycopg2 同步驱动）
"""
import os
import sys
from logging.config import fileConfig
from pathlib import Path

from alembic import context
from sqlalchemy import engine_from_config, pool

# 把 backend 目录加入 sys.path（让 alembic 能 import 项目模块）
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import settings  # noqa: E402
from db.database import Base  # noqa: E402
# 导入所有 model，确保 Base.metadata 知道所有表
from db import models  # noqa: F401, E402

# Alembic 配置
config = context.config

# 日志配置
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# 目标 metadata — 用于 autogenerate
target_metadata = Base.metadata

# 从 settings 读取 DATABASE_URL 并转换为同步 URL
def _get_sync_url() -> str:
    """将 asyncpg URL 转为 psycopg2 URL 供 alembic 使用"""
    url = settings.DATABASE_URL
    # postgresql+asyncpg://user:pass@host:port/db → postgresql://user:pass@host:port/db
    url = url.replace("postgresql+asyncpg://", "postgresql://")
    # sqlite+aiosqlite:// → sqlite://
    url = url.replace("sqlite+aiosqlite://", "sqlite://")
    return url


# 设置 sqlalchemy.url
config.set_main_option("sqlalchemy.url", _get_sync_url())


def run_migrations_offline() -> None:
    """离线模式：生成 SQL 脚本，不连接 DB"""
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
    """在线模式：连接 DB 执行迁移"""
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
