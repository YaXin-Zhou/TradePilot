"""数据库连接与会话管理 — Phase 8 稳定性加固

改动：
  - PostgreSQL 启用 pool_pre_ping（防止长连接断开）
  - SQLite 不使用连接池（避免警告）
  - 合理的连接池参数
"""
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from pathlib import Path

from config import settings

# 确保数据目录存在 (仅SQLite)
if "sqlite" in settings.DATABASE_URL:
    db_path = Path(settings.DATABASE_URL.replace("sqlite+aiosqlite:///", "")).parent
    db_path.mkdir(parents=True, exist_ok=True)

# 连接池配置：PostgreSQL 用连接池 + pre_ping，SQLite 不用
_engine_kwargs = {"echo": settings.ECHO_SQL}
if "sqlite" not in settings.DATABASE_URL:
    _engine_kwargs.update({
        "pool_size": 10,
        "max_overflow": 20,
        "pool_pre_ping": True,   # Phase 8: 防止长连接断开
        "pool_recycle": 3600,    # 1 小时回收
    })

engine = create_async_engine(settings.DATABASE_URL, **_engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


class Base(DeclarativeBase):
    pass


async def init_db():
    from db.models import User, Strategy, Order, Trade, Position, MarketData, MLPrediction
    from db.models import AuditLog, ExchangeCredential, RunnerState  # M1: 新增三张表
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        # M1: 迁移已有 orders 表 — 添加 account_id / idempotency_key / raw 字段
        await conn.run_sync(_migrate_orders_table)


def _migrate_orders_table(conn):
    """为已有 orders 表添加 M1/M3 新字段（create_all 不会 ALTER 已有表）"""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if "orders" not in inspector.get_table_names():
        return  # 表不存在（首次启动），create_all 会处理
    existing_cols = {c["name"] for c in inspector.get_columns("orders")}
    new_cols = [
        ("account_id", "VARCHAR(64) DEFAULT 'default'"),
        ("idempotency_key", "VARCHAR(128)"),
        ("raw", "JSON"),
    ]
    for col_name, col_type in new_cols:
        if col_name not in existing_cols:
            conn.execute(text(f"ALTER TABLE orders ADD COLUMN {col_name} {col_type}"))
            print(f"[M1] Migrated: orders.{col_name} added")


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def close_db():
    await engine.dispose()
