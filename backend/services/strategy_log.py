"""策略事件日志 — 内存环形缓冲区 + DB 异步持久化

每个策略最多保留 200 条最近事件，API 即时读取无延迟。
DB 持久化用于跨重启恢复和长期审计。

事件类型:
  created, started, stopped, deleted, signal_buy, signal_sell,
  order_placed, order_error, stop_loss, heartbeat, error
"""
from collections import defaultdict, deque
from datetime import datetime, timezone
from typing import Optional
import json
import threading

from core.logger import log as app_log

MAX_EVENTS = 200  # 每个策略最大保留

# 内存环形缓冲区 {strategy_id: deque([{event}, ...])}
_buffer: dict[str, deque] = defaultdict(lambda: deque(maxlen=MAX_EVENTS))
_lock = threading.Lock()

# DB 表名（通过 raw SQL 创建，避免迁移依赖）
_LOGS_TABLE = "strategy_event_logs"

# 单次写入 DB，不阻塞主流程
_db_queue: list[dict] = []
_db_lock = threading.Lock()


def _is_sqlite() -> bool:
    """检测当前是否 SQLite（本地开发默认），用于方言自适应的 DDL/INSERT"""
    from config import settings
    return "sqlite" in settings.DATABASE_URL.lower()


def append(strategy_id: str, event_type: str, msg: str, detail: Optional[dict] = None) -> dict:
    """追加一条策略日志事件。

    返回事件 dict，同步写入内存缓冲区，异步入队等待 DB 写入。
    """
    event = {
        "strategy_id": strategy_id,
        "event_type": event_type,
        "message": msg,
        "detail": detail or {},
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    with _lock:
        _buffer[strategy_id].append(event)

    # 异步入队 DB 写入
    with _db_lock:
        _db_queue.append(event)

    # 简洁的控制台日志
    app_log.info(f"[STRATEGY_LOG] {strategy_id[:8]} | {event_type:16s} | {msg}")

    return event


def get_logs(strategy_id: str, limit: int = 100, event_type: Optional[str] = None) -> list[dict]:
    """获取策略日志（最近 N 条，可按类型过滤）"""
    with _lock:
        events = list(_buffer.get(strategy_id, []))
    if event_type:
        events = [e for e in events if e["event_type"] == event_type]
    return events[-limit:]


async def _ensure_table():
    """确保日志表存在（启动时调用，方言自适应 SQLite/PG）"""
    from sqlalchemy import text
    from db.database import engine as async_engine

    if _is_sqlite():
        # SQLite：BIGSERIAL/JSONB/TIMESTAMPTZ 不可用，改用 INTEGER/TEXT/DATETIME
        create_sql = f"""
            CREATE TABLE IF NOT EXISTS {_LOGS_TABLE} (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                strategy_id VARCHAR(64) NOT NULL,
                event_type VARCHAR(32) NOT NULL,
                message TEXT,
                detail TEXT DEFAULT '{{}}',
                created_at TEXT NOT NULL DEFAULT (datetime('now'))
            );
        """
    else:
        create_sql = f"""
            CREATE TABLE IF NOT EXISTS {_LOGS_TABLE} (
                id BIGSERIAL PRIMARY KEY,
                strategy_id VARCHAR(64) NOT NULL,
                event_type VARCHAR(32) NOT NULL,
                message TEXT,
                detail JSONB DEFAULT '{{}}',
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
            );
        """
    try:
        async with async_engine.begin() as conn:
            await conn.execute(text(create_sql))
            await conn.execute(text(f"""
                CREATE INDEX IF NOT EXISTS idx_se_logs_sid
                    ON {_LOGS_TABLE}(strategy_id, created_at DESC);
            """))
        app_log.info("StrategyLog: table ensured")
    except Exception as e:
        app_log.warning(f"StrategyLog: ensure_table failed: {e}")


async def flush_to_db() -> int:
    """将内存队列中的事件批量写入 DB。由调度器定期调用。
    返回写入条数。
    """
    global _db_queue
    with _db_lock:
        batch = _db_queue
        _db_queue = []
    if not batch:
        return 0

    try:
        from sqlalchemy import text
        from db.database import async_session

        # 方言自适应：SQLite 的 detail 存 TEXT，PG 存 JSONB（CAST）
        if _is_sqlite():
            insert_sql = (
                f"INSERT INTO {_LOGS_TABLE} (strategy_id, event_type, message, detail, created_at) "
                "VALUES (:sid, :etype, :msg, :detail, :ts)"
            )
        else:
            insert_sql = (
                f"INSERT INTO {_LOGS_TABLE} (strategy_id, event_type, message, detail, created_at) "
                "VALUES (:sid, :etype, :msg, CAST(:detail AS jsonb), :ts)"
            )

        async with async_session() as session:
            async with session.begin():
                for ev in batch:
                    # created_at 从 ISO 字符串解析为 datetime
                    ts = ev["created_at"]
                    if isinstance(ts, str):
                        ts = datetime.fromisoformat(ts)
                    await session.execute(
                        text(insert_sql),
                        {
                            "sid": ev["strategy_id"],
                            "etype": ev["event_type"],
                            "msg": ev["message"],
                            "detail": json.dumps(ev["detail"]) if ev["detail"] else "{}",
                            "ts": ts,
                        },
                    )
        return len(batch)
    except Exception as e:
        app_log.warning(f"StrategyLog: flush_to_db failed ({len(batch)} events): {e}")
        # 失败的事件放回队列重试
        with _db_lock:
            _db_queue = batch + _db_queue
            if len(_db_queue) > 2000:
                _db_queue = _db_queue[-1000:]  # 防止爆内存
                app_log.error("StrategyLog: DB queue overflow, dropped 1000 oldest events")
        return 0


async def recover_from_db(strategy_id: str, limit: int = 200) -> list[dict]:
    """从 DB 恢复策略日志（应用重启后）。"""
    try:
        from sqlalchemy import text
        from db.database import async_session
        async with async_session() as session:
            result = await session.execute(
                text(f"SELECT strategy_id, event_type, message, detail, created_at "
                     f"FROM {_LOGS_TABLE} WHERE strategy_id = :sid "
                     f"ORDER BY created_at DESC LIMIT :lim"),
                {"sid": strategy_id, "lim": limit},
            )
            rows = result.fetchall()
            events = []
            for row in reversed(rows):  # 反转回正序
                # detail 可能是 dict（PG JSONB）或 JSON 字符串（SQLite TEXT），统一解析
                detail_raw = row[3]
                if isinstance(detail_raw, str):
                    try:
                        detail = json.loads(detail_raw) if detail_raw else {}
                    except (json.JSONDecodeError, TypeError):
                        detail = {}
                elif isinstance(detail_raw, dict):
                    detail = detail_raw
                else:
                    detail = {}
                events.append({
                    "strategy_id": row[0],
                    "event_type": row[1],
                    "message": row[2],
                    "detail": detail,
                    "created_at": row[4].isoformat() if row[4] else "",
                })
            if events:
                with _lock:
                    for ev in events:
                        _buffer[strategy_id].append(ev)
            return events
    except Exception as e:
        app_log.warning(f"StrategyLog: recover_from_db({strategy_id}) failed: {e}")
        return []


async def recover_all_from_db(limit_per_strategy: int = 200) -> int:
    """启动时从 DB 恢复所有策略的日志。返回恢复的策略数。"""
    try:
        from sqlalchemy import text
        from db.database import async_session
        async with async_session() as session:
            result = await session.execute(
                text(f"SELECT DISTINCT strategy_id FROM {_LOGS_TABLE}")
            )
            strategy_ids = [row[0] for row in result.fetchall()]

        recovered = 0
        for sid in strategy_ids:
            events = await recover_from_db(sid, limit=limit_per_strategy)
            if events:
                recovered += 1
                app_log.info(f"StrategyLog: recovered {len(events)} logs for {sid[:8]}")
        app_log.info(f"StrategyLog: recovery complete — {recovered} strategies, {sum(len(v) for v in _buffer.values())} total events")
        return recovered
    except Exception as e:
        app_log.warning(f"StrategyLog: recover_all_from_db failed: {e}")
        return 0
