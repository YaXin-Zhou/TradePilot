"""集成测试 — 下单 → 风控 → 成交 全链路（Phase 7.6）

验证 trading_service 正确接入 regime_detector + risk_engine：
  place_market_order → _enhanced_risk_check → _detect_regime → risk_engine.full_check → create_market_order
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import pandas as pd

from services import trading_service
from services.regime_detector import MarketRegime, RegimeResult
from db.models import StrategyType


def _make_ohlcv_df(prices: list[float], symbol: str = "BTC/USDT") -> pd.DataFrame:
    """构造上涨趋势的 OHLCV DataFrame"""
    n = len(prices)
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC"),
        "open": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "close": prices,
        "volume": [1000.0] * n,
        "symbol": symbol,
    })


@pytest.fixture
def uptrend_regime():
    """Mock regime_detector 返回 TRENDING_UP + mock fetch_ohlcv 返回数据"""
    result = RegimeResult(
        regime=MarketRegime.TRENDING_UP,
        confidence=0.85,
        ma_slope_pct=1.5,
        atr_pct=2.0,
        atr_median_pct=1.8,
        volatility_percentile=0.6,
        price=50000.0,
    )
    # _detect_regime 先调 fetch_ohlcv 再调 detect，两者都要 mock
    df = pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=60, freq="1h", tz="UTC"),
        "open": [40000 + i * 200 for i in range(60)],
        "high": [(40000 + i * 200) * 1.01 for i in range(60)],
        "low": [(40000 + i * 200) * 0.99 for i in range(60)],
        "close": [40000 + i * 200 for i in range(60)],
        "volume": [1000.0] * 60,
    })
    with patch.object(trading_service.regime_detector, "detect", return_value=result), \
         patch.object(trading_service.shared_exchange, "fetch_ohlcv", return_value=df):
        yield result


@pytest.fixture
def mock_balance():
    """Mock fetch_balance 返回 10000 USDT"""
    with patch.object(trading_service.shared_exchange, "fetch_balance",
                      return_value={"USDT": {"free": 10000, "used": 0, "total": 10000}}):
        yield


class TestTradingServiceIntegration:
    """trading_service 集成测试"""

    @pytest.mark.asyncio
    async def test_market_order_full_chain_passes_risk(self, uptrend_regime, mock_balance):
        """市价单全链路：风控通过 → 下单成功"""
        # risk_engine.full_check 在 TRENDING_UP + CUSTOM + sharpe=999 应通过
        with patch.object(trading_service.shared_exchange, "fetch_ticker",
                          return_value={"last": 50000}), \
             patch.object(trading_service.shared_exchange, "create_market_order",
                          return_value={"id": "ord123", "status": "closed", "amount": 0.01}):
            order, err, is_mock = await trading_service.place_market_order(
                "user1", "BTC/USDT", "buy", 0.01
            )
        assert err is None
        assert order["id"] == "ord123"
        assert is_mock is False

    @pytest.mark.asyncio
    async def test_market_order_blocked_by_risk(self, uptrend_regime, mock_balance):
        """市价单金额超限 → 风控拦截 → 不下单"""
        # TRENDING_UP max_position_pct=0.40 → max 4000 USDT
        # 100 BTC × 50000 = 5,000,000 USDT 远超 4000
        with patch.object(trading_service.shared_exchange, "fetch_ticker",
                          return_value={"last": 50000}), \
             patch.object(trading_service.shared_exchange, "create_market_order") as mock_order:
            order, err, is_mock = await trading_service.place_market_order(
                "user1", "BTC/USDT", "buy", 100
            )
        assert order is None
        assert err is not None
        assert "RiskEngine" in err or "exceeds" in err.lower() or "position" in err.lower()
        mock_order.assert_not_called()

    @pytest.mark.asyncio
    async def test_limit_order_full_chain(self, uptrend_regime, mock_balance):
        """限价单全链路：风控通过 → 下单成功"""
        # 0.01 BTC × 50000 = 500 USDT < 4000 限额
        with patch.object(trading_service.shared_exchange, "create_limit_order",
                          return_value={"id": "lim456", "status": "open"}):
            order, err, is_mock = await trading_service.place_limit_order(
                "user1", "BTC/USDT", "buy", 0.01, 50000
            )
        assert err is None
        assert order["id"] == "lim456"

    @pytest.mark.asyncio
    async def test_zero_amount_rejected(self, uptrend_regime, mock_balance):
        """零金额下单被拦截"""
        order, err, is_mock = await trading_service.place_market_order(
            "user1", "BTC/USDT", "buy", 0
        )
        assert order is None
        assert "positive" in err.lower()

    @pytest.mark.asyncio
    async def test_regime_detect_fallback_on_error(self, mock_balance):
        """regime detect 异常 → 回退 RANGING_LOW_VOL → 仍走 risk_engine"""
        # fetch_ohlcv 抛异常 → _detect_regime 返回 RANGING_LOW_VOL
        with patch.object(trading_service.shared_exchange, "fetch_ohlcv",
                          side_effect=RuntimeError("network")), \
             patch.object(trading_service.shared_exchange, "fetch_ticker",
                          return_value={"last": 50000}), \
             patch.object(trading_service.shared_exchange, "create_market_order",
                          return_value={"id": "ok", "status": "closed"}):
            # RANGING_LOW_VOL allowed=[grid, ma_cross], CUSTOM 不在 → 被拦截
            order, err, is_mock = await trading_service.place_market_order(
                "user1", "BTC/USDT", "buy", 0.001
            )
        # CUSTOM 在 RANGING_LOW_VOL 被 regime_allowed 拦截
        assert order is None
        assert err is not None

    @pytest.mark.asyncio
    async def test_mock_fallback_on_order_exception(self, uptrend_regime, mock_balance):
        """下单异常 → mock 回退"""
        with patch.object(trading_service.shared_exchange, "fetch_ticker",
                          return_value={"last": 50000}), \
             patch.object(trading_service.shared_exchange, "create_market_order",
                          side_effect=RuntimeError("exchange down")):
            order, err, is_mock = await trading_service.place_market_order(
                "user1", "BTC/USDT", "buy", 0.001
            )
        # 风控通过但下单失败 → mock 回退
        assert order is not None
        assert is_mock is True
        assert err is None

    @pytest.mark.asyncio
    async def test_total_capital_from_balance(self, uptrend_regime):
        """_get_total_capital 从 balance 获取总资金"""
        with patch.object(trading_service.shared_exchange, "fetch_balance",
                          return_value={"USDT": {"total": 25000}}):
            total = await trading_service._get_total_capital()
        assert total == 25000

    @pytest.mark.asyncio
    async def test_enhanced_risk_check_uses_regime(self, uptrend_regime, mock_balance):
        """_enhanced_risk_check 正确调用 regime_detector 和 risk_engine"""
        with patch.object(trading_service.shared_exchange, "fetch_ticker",
                          return_value={"last": 50000}):
            # 500 USDT 在 TRENDING_UP (max 4000) 通过
            ok, msg = await trading_service._enhanced_risk_check(
                "user1", "BTC/USDT", "buy", 500
            )
        assert ok is True
        assert msg == ""
