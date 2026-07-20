"""T1: rate_limiter 限流逻辑测试"""
import sys
import os
import asyncio
import pytest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


class TestRateLimiter:
    @pytest.mark.asyncio
    async def test_allow_first_request(self):
        with patch("core.rate_limiter.RateLimiter._get_redis", return_value=None):
            from core.rate_limiter import RateLimiter
            limiter = RateLimiter(requests_per_minute=60, burst=5)
            allowed = await limiter.check("test_key_1", 60)
            assert allowed

    @pytest.mark.asyncio
    async def test_block_after_burst(self):
        with patch("core.rate_limiter.RateLimiter._get_redis", return_value=None):
            from core.rate_limiter import RateLimiter
            limiter = RateLimiter(requests_per_minute=60, burst=3)
            results = []
            for _ in range(10):
                results.append(await limiter.check("burst_key", 60))
            allowed_count = sum(1 for r in results if r)
            assert allowed_count <= 3
            assert not all(results)

    @pytest.mark.asyncio
    async def test_refill_after_wait(self):
        with patch("core.rate_limiter.RateLimiter._get_redis", return_value=None):
            from core.rate_limiter import RateLimiter
            limiter = RateLimiter(requests_per_minute=120, burst=5)
            for _ in range(5):
                await limiter.check("refill_key", 120)
            assert not await limiter.check("refill_key", 120)
            await asyncio.sleep(0.7)
            assert await limiter.check("refill_key", 120)


class TestSensitiveLimits:
    def test_login_has_lower_limit(self):
        from core.rate_limiter import SENSITIVE_LIMITS, limiter
        assert "/api/auth/login" in SENSITIVE_LIMITS
        assert SENSITIVE_LIMITS["/api/auth/login"] < limiter.rpm

    def test_trading_has_lower_limit(self):
        from core.rate_limiter import SENSITIVE_LIMITS
        assert "/api/trading/market-order" in SENSITIVE_LIMITS
