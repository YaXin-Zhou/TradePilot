"""集成测试 — 策略 runner tick → 风控 → 止损 全链路（Phase 7.6）

验证 strategies/runner.py 正确接入 regime_detector + risk_engine + stop_loss_manager + portfolio_allocator
"""
import pytest
import asyncio
import pandas as pd
from unittest.mock import patch, MagicMock, AsyncMock
from datetime import datetime, timezone

from strategies.runner import StrategyRunner
from strategies.base import SignalType
from services.regime_detector import MarketRegime, RegimeResult
from services.stop_loss import StopLossManager, StopLossConfig, StopReason
from db.models import StrategyType
from core.tick_cache import tick_cache


def _uptrend_ohlcv(symbol: str = "BTC/USDT") -> pd.DataFrame:
    """构造 60 行上涨趋势 OHLCV（MA50 斜率 > 0.5%）"""
    prices = [40000 + i * 200 for i in range(60)]  # 40000 → 51800
    return pd.DataFrame({
        "timestamp": pd.date_range("2026-01-01", periods=60, freq="1h", tz="UTC"),
        "open": prices,
        "high": [p * 1.01 for p in prices],
        "low": [p * 0.99 for p in prices],
        "close": prices,
        "volume": [1000.0] * 60,
        "symbol": symbol,
    })


def _make_strategy_obj(symbol="BTC/USDT", signal_type=SignalType.BUY,
                       stype=StrategyType.MA_CROSS, sharpe=1.5):
    """构造 mock 策略对象"""
    obj = MagicMock()
    obj.symbol = symbol
    obj.strategy_type = stype
    obj.sharpe_oos = sharpe
    obj.analyze = AsyncMock(return_value=MagicMock(type=signal_type))
    return obj


@pytest.fixture
def runner():
    return StrategyRunner()


@pytest.fixture
def mock_exchange():
    """Mock shared_exchange 的所有网络调用"""
    patches = [
        patch("core.exchange.shared_exchange.fetch_ticker",
              return_value={"last": 50000}),
        patch("core.exchange.shared_exchange.fetch_ohlcv",
              return_value=_uptrend_ohlcv()),
        patch("core.exchange.shared_exchange.fetch_balance",
              return_value={"USDT": {"total": 10000}}),
        patch("core.exchange.shared_exchange.create_market_order",
              return_value={"id": "ord1", "status": "closed"}),
    ]
    for p in patches:
        p.start()
    yield
    for p in patches:
        p.stop()


@pytest.fixture
def mock_pool_weight():
    """Mock strategy_pool.get 返回权重 0.1"""
    s = MagicMock()
    s.weight = 0.1
    with patch("services.strategy_pool.strategy_pool.get", return_value=s):
        yield


class TestRunnerIntegration:
    """runner 集成测试"""

    @pytest.mark.asyncio
    async def test_tick_full_chain_places_order(self, runner, mock_exchange, mock_pool_weight):
        """tick 全链路：信号 → regime → 风控 → 分配 → 下单 → 初始化止损"""
        obj = _make_strategy_obj()
        await runner._tick("strat1", obj)

        # 验证下单被调用
        from core.exchange import shared_exchange
        # create_market_order 被调用（通过 to_thread）
        assert shared_exchange.create_market_order.called
        # 止损管理器已初始化
        assert "strat1" in runner._stop_managers
        # 持仓已记录
        assert "strat1" in runner._positions_usdt
        assert "strat1" in runner._positions_qty

    @pytest.mark.asyncio
    async def test_tick_hold_signal_no_order(self, runner, mock_exchange, mock_pool_weight):
        """HOLD 信号 → 不下单"""
        obj = _make_strategy_obj(signal_type=SignalType.HOLD)
        await runner._tick("strat1", obj)
        from core.exchange import shared_exchange
        assert not shared_exchange.create_market_order.called

    @pytest.mark.asyncio
    async def test_tick_risk_blocked_no_order(self, runner, mock_exchange, mock_pool_weight):
        """风控拦截 → 不下单（TRENDING_DOWN + MA_CROSS 不在 allowed）"""
        # Mock regime 为 TRENDING_DOWN（allowed=[rsi]，MA_CROSS 被拦）
        result = RegimeResult(
            regime=MarketRegime.TRENDING_DOWN, confidence=0.8,
            ma_slope_pct=-1.5, atr_pct=2.0, atr_median_pct=1.8,
            volatility_percentile=0.6, price=50000,
        )
        with patch("strategies.runner.regime_detector.detect", return_value=result):
            obj = _make_strategy_obj(stype=StrategyType.MA_CROSS)
            await runner._tick("strat1", obj)
        from core.exchange import shared_exchange
        assert not shared_exchange.create_market_order.called

    @pytest.mark.asyncio
    async def test_stop_loss_triggers_close(self, runner, mock_exchange, mock_pool_weight):
        """止损触发 → 平仓 → 清理状态"""
        # 先开仓
        obj = _make_strategy_obj()
        await runner._tick("strat1", obj)
        assert "strat1" in runner._stop_managers

        # 模拟价格暴跌触发硬止损
        runner._positions_qty["strat1"] = 0.01  # 持仓 0.01 BTC
        sm = runner._stop_managers["strat1"]
        # hard_stop_pct 默认 8%，entry=50000，跌到 45000 = -10%
        with patch("core.exchange.shared_exchange.fetch_ticker",
                   return_value={"last": 45000}):
            obj.analyze = AsyncMock(return_value=MagicMock(type=SignalType.HOLD))
            await runner._tick("strat1", obj)

        # 止损后状态清理
        assert "strat1" not in runner._stop_managers
        assert "strat1" not in runner._positions_qty

    @pytest.mark.asyncio
    async def test_tick_exception_does_not_crash(self, runner):
        """fetch_ticker 异常 → 记录日志不崩溃（修复 except: pass）"""
        # v2.0: 清空 tick_cache，避免上一个测试的缓存命中导致异常不触发
        tick_cache.invalidate()
        with patch("core.exchange.shared_exchange.fetch_ticker",
                   side_effect=RuntimeError("network down")):
            # _tick 内部不 catch 通用异常（由 _run_loop catch）
            # 这里直接调 _tick 验证它抛出，_run_loop 会 catch
            with pytest.raises(RuntimeError):
                await runner._tick("strat1", _make_strategy_obj())

    @pytest.mark.asyncio
    async def test_run_loop_catches_tick_errors(self, runner, mock_exchange, mock_pool_weight):
        """_run_loop 捕获 tick 异常并继续（修复异常吞噬）

        验证：_tick 抛 RuntimeError 被 _run_loop 的 except catch（不崩溃），
        然后 asyncio.sleep 抛 CancelledError 让循环退出。
        """
        call_count = 0

        async def flaky_tick(sid, obj):
            nonlocal call_count
            call_count += 1
            raise RuntimeError("tick fails")  # 每次都抛

        async def fast_sleep(_seconds):
            raise asyncio.CancelledError()  # sleep 立即退出循环

        with patch("asyncio.sleep", new=fast_sleep), \
             patch.object(runner, "_tick", side_effect=flaky_tick):
            obj = _make_strategy_obj()
            task = asyncio.create_task(runner._run_loop("strat1", obj))
            try:
                await task
            except asyncio.CancelledError:
                pass
        # _tick 被调用至少一次（异常被 catch，没崩溃）
        assert call_count >= 1

    @pytest.mark.asyncio
    async def test_close_position_uses_recorded_qty(self, runner, mock_exchange):
        """平仓使用记录的持仓数量（非硬编码 0.001）"""
        runner._positions_qty["strat1"] = 0.05
        runner._positions_usdt["strat1"] = 2500
        sm = StopLossManager(StopLossConfig(hard_stop_pct=8.0), 50000)
        sm.set_side("long")
        runner._stop_managers["strat1"] = sm

        await runner._close_position("strat1", "BTC/USDT", "long")

        from core.exchange import shared_exchange
        # 验证下单数量是 0.05（记录的），不是 0.001
        args = shared_exchange.create_market_order.call_args
        assert args[0][2] == 0.05  # 第3个位置参数 = amount
        # 状态清理
        assert "strat1" not in runner._positions_qty

    @pytest.mark.asyncio
    async def test_strategy_weight_from_pool(self, runner, mock_exchange):
        """策略权重从 strategy_pool 获取"""
        s = MagicMock()
        s.weight = 0.25
        with patch("services.strategy_pool.strategy_pool.get", return_value=s):
            w = runner._get_strategy_weight("strat1")
        assert w == 0.25

    @pytest.mark.asyncio
    async def test_strategy_weight_default_when_pool_empty(self, runner, mock_exchange):
        """策略池无记录 → 默认权重 0.1"""
        with patch("services.strategy_pool.strategy_pool.get", return_value=None):
            w = runner._get_strategy_weight("strat1")
        assert w == 0.1

    @pytest.mark.asyncio
    async def test_resolve_strategy_type(self, runner):
        """_resolve_strategy_type 正确处理枚举/字符串/None"""
        # 枚举
        obj = MagicMock()
        obj.strategy_type = StrategyType.GRID
        assert runner._resolve_strategy_type(obj) == "grid"
        # 字符串
        obj.strategy_type = "rsi"
        assert runner._resolve_strategy_type(obj) == "rsi"
        # None → CUSTOM
        obj.strategy_type = None
        assert runner._resolve_strategy_type(obj) == "custom"
        # 无属性 → CUSTOM
        obj2 = MagicMock(spec=[])
        assert runner._resolve_strategy_type(obj2) == "custom"
