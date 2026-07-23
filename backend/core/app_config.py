"""应用配置 KV 存储 — 读缓存 + 异步写 DB"""
import json
import threading
from core.logger import log

MANUAL_RISK_DEFAULTS = {
    "max_order_usdt": 0,       # 0 = 不限制（0=关闭）
    "max_daily_loss_usdt": 0,  # 0 = 不限制
    "min_order_usdt": 0,       # 0 = 不限制
    "max_position_usdt": 0,    # 0 = 不限制
    "enabled": False,          # 默认关闭，用户手动开启
}

_cache: dict[str, dict] = {}
_lock = threading.Lock()


def _load_from_db(key: str) -> dict:
    """从 DB 加载配置项"""
    import asyncio
    from sqlalchemy import text
    from db.database import async_session

    async def _read():
        try:
            async with async_session() as session:
                result = await session.execute(
                    text("SELECT value FROM app_config WHERE key = :key"),
                    {"key": key},
                )
                row = result.fetchone()
                if row:
                    val = row[0]
                    return json.loads(val) if isinstance(val, str) else val
        except Exception as e:
            log.warning(f"app_config: load {key} failed: {e}")
        return None

    try:
        return asyncio.run(_read())
    except RuntimeError:
        return None


def get_manual_risk() -> dict:
    """获取手动交易风控设置（带缓存，按需从 DB 加载）"""
    key = "manual_risk_settings"
    with _lock:
        if key not in _cache:
            db_val = _load_from_db(key)
            _cache[key] = db_val if db_val else MANUAL_RISK_DEFAULTS.copy()
        return _cache[key]


def refresh_cache(key: str | None = None):
    """强制刷新缓存"""
    with _lock:
        if key:
            _cache.pop(key, None)
        else:
            _cache.clear()
