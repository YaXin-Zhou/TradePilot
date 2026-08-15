"""Redis 连接管理 — v1.2 生产级组件

提供连接池管理的 Redis 客户端，供 rate_limiter、cache 等模块复用。
Redis 包未安装时优雅降级（返回 None）。
"""

from config import settings
from core.logger import log

_redis = None
_redis_unavailable: bool = False


async def get_redis():
    """获取 Redis 客户端（自动连接 + 故障检测）

    返回 None 表示 Redis 不可用，调用方应降级。
    """
    global _redis, _redis_unavailable

    if _redis_unavailable:
        return None

    if _redis is not None:
        try:
            await _redis.ping()
            return _redis
        except Exception:
            log.warning("Redis ping failed, reconnecting...")
            _redis = None

    # 检查 Redis 包是否安装
    try:
        import redis.asyncio as aioredis
    except ImportError:
        log.warning("redis package not installed, using in-memory fallback")
        _redis_unavailable = True
        return None

    # 尝试连接
    try:
        redis_url = getattr(settings, "REDIS_URL", "redis://redis:6379/0")
        if not redis_url:
            _redis_unavailable = True
            return None

        _redis = aioredis.from_url(
            redis_url,
            encoding="utf-8",
            decode_responses=False,
            max_connections=10,
            socket_connect_timeout=3,
            socket_keepalive=True,
            health_check_interval=30,
        )
        await _redis.ping()
        # v2.0: 日志脱敏 — 只打印 host，避免明文泄漏含密码的 Redis URL
        _safe_host = "unknown"
        try:
            from urllib.parse import urlparse
            parsed = urlparse(redis_url)
            _safe_host = parsed.hostname or "unknown"
        except Exception:
            pass
        log.info(f"Redis connected: host={_safe_host}")
        return _redis
    except Exception as e:
        log.warning(f"Redis unavailable ({e}), falling back to in-memory mode")
        _redis_unavailable = True
        _redis = None
        return None


async def close_redis():
    """关闭 Redis 连接（shutdown 时调用）"""
    global _redis
    if _redis is not None:
        try:
            await _redis.close()
        except Exception:
            pass
        _redis = None
