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
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def close_db():
    await engine.dispose()
