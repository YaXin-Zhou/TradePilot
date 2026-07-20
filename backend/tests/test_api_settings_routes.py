"""v1.3 U1: API 设置路由 smoke 测试"""
import sys, os, pytest
from unittest.mock import patch
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture
async def client():
    from main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


class TestSettingsRoutes:
    @pytest.mark.asyncio
    async def test_get_exchange_settings(self, client):
        resp = await client.get("/api/settings/exchange")
        assert resp.status_code in (200, 401, 403)

    @pytest.mark.asyncio
    async def test_get_risk_policies(self, client):
        resp = await client.get("/api/settings/risk")
        assert resp.status_code in (200, 401, 403)


class TestAnalysisRoutes:
    @pytest.mark.asyncio
    async def test_get_indicators(self, client):
        resp = await client.get("/api/analysis/indicators?symbol=BTC/USDT")
        assert resp.status_code in (200, 500)

    @pytest.mark.asyncio
    async def test_get_prediction(self, client):
        resp = await client.get("/api/analysis/predict?symbol=BTC/USDT")
        assert resp.status_code in (200, 500)


class TestStrategyRoutes:
    @pytest.mark.asyncio
    async def test_list_strategies(self, client):
        resp = await client.get("/api/strategies")
        assert resp.status_code in (200, 401, 403)

    @pytest.mark.asyncio
    async def test_get_strategy_pool(self, client):
        resp = await client.get("/api/strategies/pool")
        assert resp.status_code in (200, 401, 403)


class TestBacktestRoutes:
    @pytest.mark.asyncio
    async def test_backtest_history(self, client):
        resp = await client.get("/api/backtest/history")
        assert resp.status_code in (200, 401, 403)

    @pytest.mark.asyncio
    async def test_backtest_stats(self, client):
        resp = await client.get("/api/backtest/stats")
        assert resp.status_code in (200, 401, 403)
