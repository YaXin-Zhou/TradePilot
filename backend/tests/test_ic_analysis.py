"""IC/ICIR 检验测试"""
import sys
import os
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from services.ic_analysis import (
    forward_returns, compute_ic, compute_icir, analyze_ohlcv_factors,
)


def _make_ohlcv(n=300, trend=0.001):
    rng = np.random.RandomState(42)
    closes = [100.0]
    for _ in range(n - 1):
        closes.append(closes[-1] * (1 + trend + rng.normal(0, 0.005)))
    ts = pd.date_range("2026-01-01", periods=n, freq="1h", tz="UTC")
    return [
        {"timestamp": t, "open": c, "high": c * 1.001, "low": c * 0.999, "close": c,
         "volume": float(rng.uniform(100, 200))}
        for t, c in zip(ts, closes)
    ]


class TestForwardReturns:
    def test_forward_returns_1h(self):
        closes = np.array([100, 101, 102, 103], dtype=np.float64)
        rets = forward_returns(closes, horizon=1)
        assert abs(rets[0] - 0.01) < 1e-9
        assert np.isnan(rets[-1])

    def test_forward_returns_horizon_2(self):
        closes = np.array([100, 101, 102, 103], dtype=np.float64)
        rets = forward_returns(closes, horizon=2)
        assert abs(rets[0] - 0.02) < 1e-9


class TestIC:
    def test_positive_correlation(self):
        rng = np.random.RandomState(0)
        factor = np.linspace(0, 1, 100)
        returns = factor + rng.normal(0, 0.01, 100)
        assert compute_ic(factor, returns) > 0.5

    def test_random_factor_near_zero(self):
        rng = np.random.RandomState(1)
        factor = rng.normal(0, 1, 200)
        returns = rng.normal(0, 1, 200)
        assert abs(compute_ic(factor, returns)) < 0.3

    def test_icir_sufficient_data(self):
        rng = np.random.RandomState(2)
        factor = np.linspace(0, 1, 300)
        returns = factor + rng.normal(0, 0.01, 300)
        icir = compute_icir(factor, returns)
        assert np.isfinite(icir)

    def test_icir_nan_on_short(self):
        rng = np.random.RandomState(3)
        assert np.isnan(compute_icir(rng.normal(0, 1, 10), rng.normal(0, 1, 10)))


class TestAnalyzeFactors:
    def test_analyze_returns_report(self):
        data = _make_ohlcv(n=300)
        report = analyze_ohlcv_factors(data, horizon=1)
        assert "rsi_14" in report
        assert "macd_hist" in report
        assert "volume_ratio" in report
        for name, r in report.items():
            assert "ic" in r and "icir" in r
            assert r["ic"] is None or -1.0 <= r["ic"] <= 1.0

    def test_analyze_insufficient_data(self):
        assert analyze_ohlcv_factors([], horizon=1) == {}
