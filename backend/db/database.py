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
    from db.models import KillSwitchStateRecord, RiskPolicyRecord     # P0-1: JSON 迁 DB

    # N4: 优先尝试 Alembic 迁移（生产推荐方式）
    alembic_ok = await _try_alembic_upgrade()

    if not alembic_ok:
        # 回退方案：create_all + 运行时 ALTER（开发模式兜底）
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
            # M1: 迁移已有 orders 表 — 添加 account_id / idempotency_key / raw 字段
            await conn.run_sync(_migrate_orders_table)
            # v2.0: 迁移已有 users 表 — 添加 is_admin 字段（RBAC）
            await conn.run_sync(_migrate_users_table)

        # P0-2: PostgreSQL 枚举补值（必须在事务外运行，ALTER TYPE ADD VALUE 在 PG<12 不支持事务）
        await _migrate_strategytype_enum()

    # P0-1: 从 JSON 文件迁移旧数据到 DB（一次性）
    await _migrate_json_to_db()


async def _try_alembic_upgrade() -> bool:
    """N4: 尝试运行 alembic upgrade head

    成功返回 True，失败返回 False 由调用方回退。
    生产部署推荐：先 `alembic upgrade head` 再启动 uvicorn，本函数作为兜底。

    v1.3 fix: 多 worker 并发启动时，用文件锁保证只有一个 worker 执行迁移，
    其余 worker 等待并跳过（避免 4 个 Alembic 同时跑造成 DB 锁竞争）。
    锁超时 120s，超时后 worker 回退到 create_all。
    """
    import time as _time
    from pathlib import Path
    import sys

    backend_dir = Path(__file__).parent.parent
    alembic_ini = backend_dir / "alembic.ini"
    if not alembic_ini.exists():
        return False

    # v2.0: Windows 无 fcntl，跳过文件锁（本地开发单进程，无多 worker 竞态）
    try:
        import fcntl
        _has_fcntl = True
    except ImportError:
        _has_fcntl = False

    lock_fd = None
    if _has_fcntl:
        lock_file = backend_dir / "data" / ".init.lock"
        lock_file.parent.mkdir(parents=True, exist_ok=True)
        lock_fd = open(str(lock_file), "w")
        try:
            # 非阻塞尝试获取锁 → 如果已有 worker 在迁移，直接跳过
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            # 另一个 worker 正在执行迁移，等待它完成
            waited = 0
            while waited < 120:
                _time.sleep(1)
                waited += 1
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except (BlockingIOError, OSError):
                    pass
            else:
                # 等待超时，回退到 create_all
                lock_fd.close()
                return False

    try:
        from alembic.config import Config
        from alembic import command

        if str(backend_dir) not in sys.path:
            sys.path.insert(0, str(backend_dir))

        alembic_cfg = Config(str(alembic_ini))
        command.upgrade(alembic_cfg, "head")
        return True
    except ImportError:
        return False
    except Exception as e:
        try:
            from core.logger import log
            log.warning(f"Alembic upgrade failed, falling back to create_all: {e}")
        except ImportError:
            print(f"[init_db] Alembic upgrade failed, falling back to create_all: {e}")
        return False
    finally:
        if lock_fd is not None:
            lock_fd.close()


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


def _migrate_users_table(conn):
    """v2.0: 为已有 users 表添加 is_admin 字段（RBAC）"""
    from sqlalchemy import inspect, text
    inspector = inspect(conn)
    if "users" not in inspector.get_table_names():
        return
    existing_cols = {c["name"] for c in inspector.get_columns("users")}
    if "is_admin" not in existing_cols:
        conn.execute(text("ALTER TABLE users ADD COLUMN is_admin BOOLEAN DEFAULT FALSE"))
        print("[v2.0] Migrated: users.is_admin added")


async def _migrate_strategytype_enum():
    """P0-2: 为 PostgreSQL strategytype 枚举补值（MA_CROSS/RSI/BOLLINGER/AI_GENERATED）

    旧版 DB 的 strategytype 枚举只有 GRID/ML_SIGNAL/SMA_CROSS/CUSTOM，
    但 Python 枚举已有 8 个值。create_all 不会 ALTER 已有 enum type，
    需要手动 ALTER TYPE ADD VALUE。

    SQLite 没有原生 enum（用 VARCHAR 存储），跳过。
    ALTER TYPE ADD VALUE 在 PG<12 不能在事务中运行，使用 AUTOCOMMIT。
    """
    if "sqlite" in settings.DATABASE_URL:
        return  # SQLite 无原生 enum

    from sqlalchemy import text

    missing_values = ["MA_CROSS", "RSI", "BOLLINGER", "AI_GENERATED"]

    # AUTOCOMMIT 模式：ALTER TYPE ADD VALUE 不能在事务中运行（PG<12）
    async with engine.connect() as conn:
        await conn.execution_options(isolation_level="AUTOCOMMIT")

        # 1) 检查枚举类型是否存在 + 当前有哪些值
        try:
            result = await conn.execute(
                text(
                    "SELECT enumlabel FROM pg_enum WHERE enumtypid = "
                    "(SELECT oid FROM pg_type WHERE typname = 'strategytype')"
                )
            )
            existing = {row[0] for row in result}
        except Exception:
            return  # 类型不存在（首次启动 create_all 会创建完整枚举）

        if not existing:
            return

        # 2) 补缺失值（IF NOT EXISTS 保证幂等）
        for val in missing_values:
            if val not in existing:
                try:
                    await conn.execute(
                        text(f"ALTER TYPE strategytype ADD VALUE IF NOT EXISTS '{val}'")
                    )
                    print(f"[P0-2] strategytype enum + {val}")
                    existing.add(val)
                except Exception as e:
                    # 非致命：仅警告，不阻断启动
                    print(f"[P0-2] WARN: strategytype + {val} failed: {e}")


async def _migrate_json_to_db():
    """P0-1: 从 JSON 文件迁移旧数据到 DB（一次性，幂等）

    将 kill_switch.json 和 risk_policies.json 中的旧数据导入 DB 表。
    迁移成功后重命名 JSON 文件为 .migrated（保留备份，不删除）。
    """
    import json
    from pathlib import Path
    from db.models import KillSwitchStateRecord, RiskPolicyRecord

    data_dir = Path(settings.ROOT) / "data"
    ks_file = data_dir / "kill_switch.json"
    rp_file = data_dir / "risk_policies.json"

    async with async_session() as session:
        # 1) 迁移 kill_switch.json
        if ks_file.exists():
            try:
                raw = json.loads(ks_file.read_text(encoding="utf-8"))
                existing = await session.get(KillSwitchStateRecord, 1)
                if not existing:
                    record = KillSwitchStateRecord(
                        id=1,
                        status=raw.get("status", "ARMED"),
                        triggered_at=raw.get("triggered_at"),
                        triggered_by=raw.get("triggered_by"),
                        reason=raw.get("reason"),
                        actions_taken=raw.get("actions_taken", []),
                        orders_cancelled=raw.get("orders_cancelled", 0),
                        positions_closed=raw.get("positions_closed", 0),
                        strategies_stopped=raw.get("strategies_stopped", 0),
                    )
                    session.add(record)
                    await session.commit()
                    print("[P0-1] Migrated: kill_switch.json → DB")
                # 重命名旧文件（replace 覆盖已存在的 .migrated 文件）
                ks_file.replace(ks_file.with_suffix(".json.migrated"))
            except Exception as e:
                print(f"[P0-1] WARN: kill_switch.json migration failed: {e}")

        # 2) 迁移 risk_policies.json
        if rp_file.exists():
            try:
                raw = json.loads(rp_file.read_text(encoding="utf-8"))
                for regime_key, data in raw.items():
                    from sqlalchemy import select
                    existing = await session.scalar(
                        select(RiskPolicyRecord).where(
                            RiskPolicyRecord.regime == regime_key
                        )
                    )
                    if not existing:
                        record = RiskPolicyRecord(
                            regime=regime_key,
                            max_position_pct=data.get("max_position_pct", 0.3),
                            max_single_strategy_pct=data.get("max_single_strategy_pct", 0.15),
                            max_daily_loss_pct=data.get("max_daily_loss_pct", 5.0),
                            stop_loss_pct=data.get("stop_loss_pct", 8.0),
                            trailing_stop_pct=data.get("trailing_stop_pct", 3.0),
                            min_sharpe_entry=data.get("min_sharpe_entry", 0.8),
                            max_correlation=data.get("max_correlation", 0.7),
                            time_stop_hours=data.get("time_stop_hours", 72),
                            atr_stop_multiplier=data.get("atr_stop_multiplier", 2.0),
                            allowed_strategies=data.get("allowed_strategies", []),
                        )
                        session.add(record)
                await session.commit()
                print("[P0-1] Migrated: risk_policies.json → DB")
                rp_file.replace(rp_file.with_suffix(".json.migrated"))
            except Exception as e:
                print(f"[P0-1] WARN: risk_policies.json migration failed: {e}")


async def get_session() -> AsyncSession:
    async with async_session() as session:
        yield session


async def close_db():
    await engine.dispose()
