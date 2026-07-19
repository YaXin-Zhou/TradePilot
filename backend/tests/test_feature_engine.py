"""弱信号矩阵引擎测试"""
import math
import numpy as np
import pytest
from services.feature_engine import (
    FeatureHub, PCAReducer, WeakSignalEngine,
    OpenInterestData, FearGreedData, SignalMatrixResult,
    weak_signal_engine,
)


# ------------------------------------------------------------------
# 测试数据工厂
# ------------------------------------------------------------------

def make_ohlcv(n: int = 100, trend: str = "flat") -> list[dict]:
    """生成模拟 OHLCV 数据"""
    data = []
    base = 60000.0
    for i in range(n):
        if trend == "up":
            price = base + i * 50 + np.random.normal(0, 200)
        elif trend == "down":
            price = base - i * 50 + np.random.normal(0, 200)
        else:
            price = base + np.random.normal(0, 300)
        price = max(price, 1000)
        high = price * (1 + abs(np.random.normal(0, 0.01)))
        low = price * (1 - abs(np.random.normal(0, 0.01)))
        data.append({
            "timestamp": i * 3600000,
            "open": price - np.random.normal(0, 100),
            "high": high,
            "low": low,
            "close": price,
            "volume": abs(np.random.normal(100, 20)),
        })
    return data


def make_oi_data() -> OpenInterestData:
    return OpenInterestData(
        symbol="BTC/USDT",
        oi_contracts=150000,
        oi_usd=9_000_000_000,
        oi_change_1h_pct=0.5,
        oi_change_24h_pct=2.3,
        long_short_ratio=1.2,
        ls_ratio_change_pct=1.0,
    )


def make_fg_data() -> FearGreedData:
    return FearGreedData(
        value=35,
        classification="fear",
        value_change_1d=-5,
        percentile_30d=0.4,
    )


# ------------------------------------------------------------------
# FeatureHub tests
# ------------------------------------------------------------------

class TestFeatureHub:
    def test_all_feature_names_54(self):
        names = FeatureHub.all_feature_names()
        assert len(names) == 54, f"Expected 54 features, got {len(names)}"
        assert "rsi_14" in names
        assert "fear_greed_value" in names
        assert "spread_pct" in names

    def test_extract_basic_insufficient_data(self):
        features = FeatureHub.extract_basic([])
        assert features == {}

    def test_extract_basic_flat_market(self):
        ohlcv = make_ohlcv(100, "flat")
        features = FeatureHub.extract_basic(ohlcv)
        assert len(features) >= 20
        assert "rsi_14" in features
        assert "price_vs_sma20" in features
        assert "macd_value" in features
        assert "atr_pct" in features
        assert "bollinger_width" in features

    def test_extract_basic_uptrend(self):
        ohlcv = make_ohlcv(100, "up")
        features = FeatureHub.extract_basic(ohlcv)
        assert features["price_change_24h"] > 0  # 上涨趋势
        assert features["price_vs_sma20"] > 0

    def test_extract_basic_downtrend(self):
        ohlcv = make_ohlcv(100, "down")
        features = FeatureHub.extract_basic(ohlcv)
        assert features["price_change_24h"] < 0  # 下跌趋势

    def test_rsi_extreme(self):
        """RSI 在单调上涨中应为高值"""
        ohlcv = []
        base = 60000.0
        for i in range(100):
            price = base + i * 500  # 强上涨
            ohlcv.append({
                "high": price * 1.01, "low": price * 0.99,
                "close": price, "volume": 100,
            })
        features = FeatureHub.extract_basic(ohlcv)
        assert features["rsi_14"] > 60  # 强 RSIShould be high

    def test_extend_with_oi(self):
        features = {"price_change_24h": 3.0}
        features = FeatureHub.extend_with_oi(features, make_oi_data())
        assert features["oi_change_pct"] == 2.3
        assert features["long_short_ratio"] == 1.2
        assert "oi_price_divergence" in features

    def test_extend_with_oi_none(self):
        features = {"price_change_24h": 3.0}
        features = FeatureHub.extend_with_oi(features, None)
        assert features["oi_change_pct"] == 0.0

    def test_extend_with_sentiment(self):
        features = {}
        features = FeatureHub.extend_with_sentiment(features, make_fg_data())
        assert features["fear_greed_value"] == 35.0
        assert features["fear_greed_class_encoded"] == 1.0  # fear=1
        assert features["fear_regime"] == 1.0  # fear

    def test_extend_with_sentiment_extreme_fear(self):
        fg = FearGreedData(value=15, classification="extreme_fear", value_change_1d=-10, percentile_30d=0.1)
        features = {}
        features = FeatureHub.extend_with_sentiment(features, fg)
        assert features["fear_greed_class_encoded"] == 0.0
        assert features["fear_regime"] == 0.0

    def test_extend_with_sentiment_none(self):
        features = {}
        features = FeatureHub.extend_with_sentiment(features, None)
        assert features["fear_greed_value"] == 0.0

    def test_extend_micro_with_orderbook(self):
        ob = {
            "bids": [["60000", "1.5"], ["59900", "2.0"]],
            "asks": [["60100", "1.0"], ["60200", "1.5"]],
        }
        features = {}
        features = FeatureHub.extend_micro(features, ob)
        assert features["spread_pct"] > 0
        assert "orderbook_imbalance" in features
        assert "depth_ratio" in features

    def test_extend_micro_none(self):
        features = {}
        features = FeatureHub.extend_micro(features, None)
        assert features["spread_pct"] == 0.0


# ------------------------------------------------------------------
# PCAReducer tests
# ------------------------------------------------------------------

class TestPCAReducer:
    def test_fit_transform_simple(self):
        reducer = PCAReducer(target_variance=0.95)
        # 5 samples, 4 features
        data = np.array([
            [1.0, 2.0, 3.0, 4.0],
            [2.0, 3.0, 4.0, 5.0],
            [3.0, 4.0, 5.0, 6.0],
            [4.0, 5.0, 6.0, 7.0],
            [5.0, 6.0, 7.0, 8.0],
        ], dtype=np.float64)
        transformed, n_components, explained_var = reducer.fit_transform(data)
        assert transformed.shape[0] == 5
        assert n_components >= 1
        assert 0.0 < explained_var <= 1.0

    def test_fit_transform_highly_correlated(self):
        """高度相关的特征应被压缩到较少主成分"""
        reducer = PCAReducer(target_variance=0.95)
        np.random.seed(42)
        x = np.linspace(0, 10, 20)
        data = np.column_stack([
            x + np.random.normal(0, 0.1, 20),   # 高度相关
            x * 2 + np.random.normal(0, 0.1, 20),
            x * 3 + np.random.normal(0, 0.1, 20),
            x * 4 + np.random.normal(0, 0.1, 20),
        ])
        transformed, n_components, explained_var = reducer.fit_transform(data)
        assert n_components <= 2  # 高度相关，1-2 个主成分即可

    def test_fit_transform_empty(self):
        reducer = PCAReducer()
        transformed, n, var = reducer.fit_transform(np.array([]))
        assert n == 0

    def test_fit_transform_single_row(self):
        reducer = PCAReducer()
        transformed, n, var = reducer.fit_transform(np.array([[1, 2, 3]]))
        assert n == 3  # 单行无法降维

    def test_transform_after_fit(self):
        reducer = PCAReducer(target_variance=0.95)
        train = np.random.randn(20, 5)
        reducer.fit_transform(train)
        new = np.random.randn(3, 5)
        result = reducer.transform(new)
        assert result.ndim == 2
        assert result.shape[0] == 3


# ------------------------------------------------------------------
# WeakSignalEngine tests
# ------------------------------------------------------------------

class TestWeakSignalEngine:
    def setup_method(self):
        weak_signal_engine.clear_cache()
        weak_signal_engine._feature_history = []

    def test_compute_full_pipeline(self):
        ohlcv = make_ohlcv(100, "flat")
        result = weak_signal_engine.compute(
            ohlcv, "BTC/USDT", make_oi_data(), make_fg_data()
        )
        assert result.symbol == "BTC/USDT"
        assert result.feature_count_total > 40
        assert result.feature_count_selected > 30
        assert result.oi_data is not None
        assert result.fear_greed is not None

    def test_compute_insufficient_data(self):
        result = weak_signal_engine.compute(
            [], "BTC/USDT"
        )
        assert result.feature_count_total == 0
        assert result.principal_components == []

    def test_compute_without_oi_and_fg(self):
        ohlcv = make_ohlcv(80, "up")
        result = weak_signal_engine.compute(ohlcv, "ETH/USDT")
        assert result.symbol == "ETH/USDT"
        assert result.feature_count_selected > 0
        assert result.oi_data is None

    def test_cache_hit(self):
        ohlcv = make_ohlcv(60, "flat")
        r1 = weak_signal_engine.compute(ohlcv, "CACHE_TEST")
        r2 = weak_signal_engine.compute(ohlcv, "CACHE_TEST")
        assert r1.feature_count_total == r2.feature_count_total

    def test_signal_matrix_to_dict(self):
        ohlcv = make_ohlcv(100, "flat")
        result = weak_signal_engine.compute(ohlcv, "BTC/USDT", make_oi_data(), make_fg_data())
        d = result.to_dict()
        assert d["symbol"] == "BTC/USDT"
        assert "principal_components" in d
        assert "oi_data" in d
        assert "fear_greed" in d

    def test_pca_with_history(self):
        """累积 10+ 样本后 PCA 应生效"""
        weak_signal_engine._feature_history = []
        for i in range(12):
            ohlcv = make_ohlcv(50 + i, "flat")
            result = weak_signal_engine.compute(ohlcv, "PCA_TEST")
        assert result.pca_n_components > 0
        assert 0.0 < result.pca_explained_variance <= 1.0


# ------------------------------------------------------------------
# Data Model tests
# ------------------------------------------------------------------

class TestDataModels:
    def test_oi_data_to_dict(self):
        oi = make_oi_data()
        d = oi.to_dict()
        assert d["symbol"] == "BTC/USDT"
        assert d["oi_contracts"] == 150000
        assert d["long_short_ratio"] == 1.2
        assert "timestamp" in d

    def test_fear_greed_to_dict(self):
        fg = make_fg_data()
        d = fg.to_dict()
        assert d["value"] == 35
        assert d["classification"] == "fear"
        assert d["value_change_1d"] == -5

    def test_fear_greed_classify_boundaries(self):
        assert FearGreedData.classify(10) == "extreme_fear"
        assert FearGreedData.classify(25) == "extreme_fear"
        assert FearGreedData.classify(26) == "fear"
        assert FearGreedData.classify(45) == "fear"
        assert FearGreedData.classify(46) == "neutral"
        assert FearGreedData.classify(55) == "neutral"
        assert FearGreedData.classify(56) == "greed"
        assert FearGreedData.classify(75) == "greed"
        assert FearGreedData.classify(76) == "extreme_greed"

    def test_signal_matrix_empty_result(self):
        result = weak_signal_engine._empty_result("EMPTY")
        assert result.symbol == "EMPTY"
        assert result.feature_count_total == 0
