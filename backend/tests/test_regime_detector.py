"""RegimeDetector 测试"""
import pytest
from services.regime_detector import (
    RegimeDetector, MarketRegime, RegimeResult, regime_detector,
)


def _make_ohlcv(prices: list[float], start=85000) -> list[dict]:
    """生成 OHLCV 数据"""
    data = []
    for i, p in enumerate(prices):
        data.append({
            "timestamp": i * 3600000,
            "open": p - 10,
            "high": p + 20,
            "low": p - 20,
            "close": p,
            "volume": 100,
        })
    return data


def _uptrend(n=60, start=85000, step=200) -> list[float]:
    return [start + i * step for i in range(n)]


def _downtrend(n=60, start=95000, step=200) -> list[float]:
    return [start - i * step for i in range(n)]


def _ranging(n=60, center=85000, noise=30) -> list[float]:
    """确定性低波动震荡"""
    import math
    return [center + noise * math.sin(i * 0.3) for i in range(n)]


def _ranging_volatile(n=60, center=85000, noise=300) -> list[float]:
    """高波动震荡：价格剧烈摆动 + 高低点差大"""
    import math
    prices = []
    for i in range(n):
        base = center + noise * math.sin(i * 0.5)
        # 在 base 上加随机的日内波动
        intraday = (i * 7 + 3) % 23 - 11  # 确定性"随机"日内波动
        prices.append(base + intraday * 50)
    return prices


class TestRegimeDetector:
    """市场状态检测"""

    def test_uptrend(self):
        regime_detector.clear_cache()
        prices = _uptrend(55)
        data = _make_ohlcv(prices)
        result = regime_detector.detect(data, "TEST_UP")
        assert result.regime == MarketRegime.TRENDING_UP
        assert result.confidence > 0.5
        assert result.ma_slope_pct > 0

    def test_downtrend(self):
        regime_detector.clear_cache()
        prices = _downtrend(55)
        data = _make_ohlcv(prices)
        result = regime_detector.detect(data, "TEST_DOWN")
        assert result.regime == MarketRegime.TRENDING_DOWN
        assert result.ma_slope_pct < 0

    def test_ranging_low_vol(self):
        regime_detector.clear_cache()
        prices = _ranging(55)
        data = _make_ohlcv(prices)
        result = regime_detector.detect(data, "TEST_RANGE_L")
        assert result.regime in (MarketRegime.RANGING_LOW_VOL, MarketRegime.RANGING_HIGH_VOL)

    def test_ranging_high_vol(self):
        regime_detector.clear_cache()
        prices = _ranging_volatile(55)
        data = _make_ohlcv(prices)
        result = regime_detector.detect(data, "TEST_RANGE_H")
        # 高波动震荡不应该被归类为趋势
        assert result.regime != MarketRegime.TRENDING_UP
        assert result.regime != MarketRegime.TRENDING_DOWN
        assert result.ma_slope_pct != 0
        assert result.atr_pct > 0

    def test_insufficient_data(self):
        data = _make_ohlcv([85000] * 10)
        result = regime_detector.detect(data)
        assert result.confidence == 0.0
        assert result.regime == MarketRegime.RANGING_LOW_VOL

    def test_empty_data(self):
        result = regime_detector.detect([])
        assert result.confidence == 0.0

    def test_cache(self):
        regime_detector.clear_cache()
        prices = _uptrend(55)
        data = _make_ohlcv(prices)
        r1 = regime_detector.detect(data, "CACHE")
        r2 = regime_detector.detect(data, "CACHE")
        assert r1.regime == r2.regime
        assert r1.timestamp == r2.timestamp  # 缓存命中

    def test_to_dict(self):
        prices = _uptrend(55)
        data = _make_ohlcv(prices)
        result = regime_detector.detect(data)
        d = result.to_dict()
        assert d["regime"] == "TRENDING_UP"
        assert "confidence" in d
        assert "ma_slope_pct" in d
        assert "atr_pct" in d


class TestRegimeResult:
    def test_fields(self):
        r = RegimeResult(
            regime=MarketRegime.TRENDING_UP,
            confidence=0.85,
            ma_slope_pct=1.2,
            atr_pct=2.5,
            atr_median_pct=2.0,
            volatility_percentile=0.7,
            price=86000,
        )
        assert r.confidence == 0.85
        assert r.regime == MarketRegime.TRENDING_UP
        assert r.price == 86000


class TestSMA:
    def test_sma_basic(self):
        data = [1, 2, 3, 4, 5, 6, 7, 8, 9, 10]
        sma = RegimeDetector._sma(data, 3)
        assert sma is not None
        assert len(sma) == 8
        assert abs(sma[0] - 2.0) < 0.01
        assert abs(sma[-1] - 9.0) < 0.01

    def test_sma_insufficient(self):
        sma = RegimeDetector._sma([1, 2], 5)
        assert sma is None


class TestATR:
    def test_atr_basic(self):
        n = 20
        highs = [100 + i * 2 + 5 for i in range(n)]
        lows = [100 + i * 2 - 5 for i in range(n)]
        closes = [100 + i * 2 for i in range(n)]
        atr = RegimeDetector._compute_atr(highs, lows, closes, 14)
        # n=20 → 19 TR values → 19-14+1=6 ATR values
        assert len(atr) == 6
        assert all(v > 0 for v in atr)
