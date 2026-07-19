"""轻量级速率限制中间件 — 基于令牌桶算法，内存存储"""
import time
import asyncio
from collections import defaultdict
from fastapi import Request, HTTPException, status


class RateLimiter:
    """简单令牌桶限流器"""

    def __init__(self, requests_per_minute: int = 200, burst: int = 50):
        self.rpm = requests_per_minute
        self.burst = burst
        self._buckets: dict[str, tuple[float, int]] = {}  # key -> (last_refill_time, tokens)
        self._lock = asyncio.Lock()

    async def _get_bucket(self, key: str) -> tuple[float, int]:
        async with self._lock:
            return self._buckets.get(key, (time.monotonic(), self.burst))

    async def _set_bucket(self, key: str, last_refill: float, tokens: int):
        async with self._lock:
            self._buckets[key] = (last_refill, tokens)

    async def check(self, key: str, limit: int | None = None) -> bool:
        """检查是否允许请求。返回 True=允许，False=限流"""
        rpm = limit or self.rpm
        now = time.monotonic()
        last_refill, tokens = await self._get_bucket(key)

        # 令牌桶补充：每秒补充 rpm/60 个令牌
        elapsed = now - last_refill
        refill = elapsed * (rpm / 60.0)
        tokens = min(self.burst, tokens + refill)

        if tokens >= 1:
            tokens -= 1
            await self._set_bucket(key, now, tokens)
            return True
        return False


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
