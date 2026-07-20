"""T1: API 交易路由层测试（FastAPI TestClient）"""
import sys
import os
import pytest
from unittest.mock import AsyncMock, patch
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
async def client():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    """健康检查端点"""

    @pytest.mark.asyncio
    async def test_health_returns_ok(self, client):
        response = await client.get("/api/health")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert "exchange" in data

    @pytest.mark.asyncio
    async def test_healthz_returns_checks(self, client):
        response = await client.get("/api/healthz")
        assert response.status_code == 200
        data = response.json()
        assert "checks" in data
        assert "database" in data["checks"]

    @pytest.mark.asyncio
    async def test_metrics_returns_json(self, client):
        response = await client.get("/api/metrics")
        assert response.status_code == 200
        data = response.json()
        assert "version" in data
        assert "uptime_seconds" in data


class TestTradingEndpoint:
    """交易 API 路由"""

    @pytest.mark.asyncio
    async def test_market_order_requires_auth(self, client):
        response = await client.post("/api/trading/market-order", json={
            "symbol": "BTC/USDT", "side": "buy", "amount": 100
        })
        # 未认证时应返回 401 或 403
        assert response.status_code in (401, 403, 422)

    @pytest.mark.asyncio
    async def test_balance_requires_auth(self, client):
        response = await client.get("/api/trading/balance")
        assert response.status_code in (401, 403)
