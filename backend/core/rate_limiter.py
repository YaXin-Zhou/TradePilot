"""速率限制中间件 — v1.2 Redis 后端 + 内存降级

Redis 可用时：多 worker 共享计数器（真实限流）
Redis 不可用时：自动降级为内存模式（单 worker 有效，log.warning）
"""

import time
import asyncio
from collections import defaultdict
from fastapi import Request, HTTPException, status
from core.logger import log


class RateLimiter:
    """令牌桶限流器 — Redis 优先 + 内存降级"""

    def __init__(self, requests_per_minute: int = 200, burst: int = 50):
        self.rpm = requests_per_minute
        self.burst = burst
        # 内存降级
        self._buckets: dict[str, tuple[float, int]] = {}
        self._lock = asyncio.Lock()
        self._redis_checked = False
        self._redis_available = False

    async def _get_redis(self):
        if not self._redis_checked:
            from core.redis import get_redis

            self._redis_available = (await get_redis()) is not None
            self._redis_checked = True
            if not self._redis_available:
                log.warning(
                    "Rate limiter: Redis unavailable — using in-memory fallback "
                    "(limits are per-worker, not global)"
                )
        if not self._redis_available:
            return None
        from core.redis import get_redis

        return await get_redis()

    # ──── Redis 实现（滑动窗口）────

    async def _check_redis(self, key: str, limit: int) -> bool:
        r = await self._get_redis()
        if r is None:
            return await self._check_memory(key, limit)

        now_ms = int(time.time() * 1000)
        window_ms = 60_000  # 1 分钟窗口
        redis_key = f"rate_limit:{key}:{now_ms // window_ms}"

        try:
            count = await r.incr(redis_key)
            if count == 1:
                await r.expire(redis_key, 120)  # 2 分钟 TTL（跨窗口边界容错）
            return count <= limit
        except Exception as e:
            log.error(f"Redis rate check failed: {e}, falling back to memory")
            return await self._check_memory(key, limit)

    # ──── 内存实现（令牌桶，开发用）────

    async def _get_bucket(self, key: str) -> tuple[float, int]:
        async with self._lock:
            return self._buckets.get(key, (time.monotonic(), self.burst))

    async def _set_bucket(self, key: str, last_refill: float, tokens: int):
        async with self._lock:
            self._buckets[key] = (last_refill, tokens)

    async def _check_memory(self, key: str, limit: int) -> bool:
        rpm = limit or self.rpm
        now = time.monotonic()
        last_refill, tokens = await self._get_bucket(key)

        elapsed = now - last_refill
        refill = elapsed * (rpm / 60.0)
        tokens = min(self.burst, tokens + refill)

        if tokens >= 1:
            tokens -= 1
            await self._set_bucket(key, now, tokens)
            return True
        return False

    # ──── 统一入口 ────

    async def check(self, key: str, limit: int | None = None) -> bool:
        """检查是否允许请求。返回 True=允许，False=限流"""
        effective_limit = limit or self.rpm
        return await self._check_redis(key, effective_limit)


# 全局限流器实例
limiter = RateLimiter()

# 敏感端点的较低限制
SENSITIVE_LIMITS = {
    "/api/auth/login": 10,
    "/api/auth/register": 5,
    "/api/trading/market-order": 30,
    "/api/trading/limit-order": 30,
}


async def rate_limit_middleware(request: Request, call_next):
    """FastAPI 中间件：对每个请求进行速率检查"""
    path = request.url.path.rstrip("/")
    client_ip = request.client.host if request.client else "unknown"
    key = f"{client_ip}:{path}"

    # 敏感端点用较低限制，普通端点用全局限制
    limit = SENSITIVE_LIMITS.get(path, None)

    allowed = await limiter.check(key, limit)
    if not allowed:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="请求过于频繁，请稍后重试",
        )

    response = await call_next(request)
    return response
