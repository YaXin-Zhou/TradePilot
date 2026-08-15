"""
弱信号矩阵引擎 — 多源数据融合 + PCA 降维

数据源:
  1. OKX Open Interest（持仓量 + OI 变化率 + 多空比）
  2. Fear & Greed Index（恐惧贪婪指数 + 历史分位）
  3. 衍生信号：OI 背离、期货溢价、成交量加权价格偏离

功能:
  - FeatureHub: 从 23 → 50+ 维弱信号扩展
  - PCA 降维：保留 95% 方差的主成分
  - 信号矩阵输出：替代原有 ML 特征输入
"""
from __future__ import annotations

import json
import math
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import numpy as np

from core.logger import log

# ------------------------------------------------------------------
# 数据模型
# ------------------------------------------------------------------


@dataclass
class OpenInterestData:
    """OKX 持仓 + 资金费率 + 基差数据"""
    symbol: str
    oi_contracts: float               # 当前持仓合约数
    oi_usd: float                     # 持仓价值 (USD)
    oi_change_1h_pct: float           # 1小时 OI 变化率 %
    oi_change_24h_pct: float          # 24小时 OI 变化率 %
    long_short_ratio: float           # 多空比
    ls_ratio_change_pct: float        # 多空比变化率 %
    funding_rate: float = 0.0         # v2.1: 当前资金费率（如 0.0001 = 0.01%）
    futures_basis_pct: float = 0.0    # v2.1: 期货基差 %（swap mark vs spot）
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "oi_contracts": round(self.oi_contracts, 2),
            "oi_usd": round(self.oi_usd, 2),
            "oi_change_1h_pct": round(self.oi_change_1h_pct, 4),
            "oi_change_24h_pct": round(self.oi_change_24h_pct, 4),
            "long_short_ratio": round(self.long_short_ratio, 4),
            "ls_ratio_change_pct": round(self.ls_ratio_change_pct, 4),
            "funding_rate": round(self.funding_rate, 8),
            "futures_basis_pct": round(self.futures_basis_pct, 6),
            "timestamp": self.timestamp,
        }


@dataclass
class FearGreedData:
    """恐惧贪婪指数"""
    value: int                         # 0-100，越低越恐惧
    classification: str                # extreme_fear / fear / neutral / greed / extreme_greed
    value_change_1d: int              # 日变化
    percentile_30d: float             # 30日分位数
    timestamp: float = field(default_factory=time.time)

    @classmethod
    def classify(cls, value: int) -> str:
        if value <= 25:
            return "extreme_fear"
        elif value <= 45:
            return "fear"
        elif value <= 55:
            return "neutral"
        elif value <= 75:
            return "greed"
        else:
            return "extreme_greed"

    def to_dict(self) -> dict:
        return {
            "value": self.value,
            "classification": self.classification,
            "value_change_1d": self.value_change_1d,
            "percentile_30d": round(self.percentile_30d, 4),
            "timestamp": self.timestamp,
        }


@dataclass
class SignalMatrixResult:
    """弱信号矩阵输出"""
    symbol: str
    feature_count_total: int           # 总特征数
    feature_count_selected: int        # 筛选后有效特征数
    pca_n_components: int              # PCA 主成分数
    pca_explained_variance: float      # PCA 累积解释方差
    principal_components: list[list[float]]  # 降维后的主成分
    oi_data: Optional[OpenInterestData] = None
    fear_greed: Optional[FearGreedData] = None
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "symbol": self.symbol,
            "feature_count_total": self.feature_count_total,
            "feature_count_selected": self.feature_count_selected,
            "pca_n_components": self.pca_n_components,
            "pca_explained_variance": round(self.pca_explained_variance, 4),
            "principal_components": [
                [round(v, 6) for v in pc] for pc in self.principal_components[:5]
            ],
            "oi_data": self.oi_data.to_dict() if self.oi_data else None,
            "fear_greed": self.fear_greed.to_dict() if self.fear_greed else None,
            "timestamp": self.timestamp,
        }


# ------------------------------------------------------------------
# FeatureHub — 弱信号特征工厂
# ------------------------------------------------------------------


class FeatureHub:
    """从 23 个基础指标扩展到 50+ 维弱信号"""

    # 价格动量类 (12维)
    MOMENTUM_FEATURES = [
        "price_change_1h", "price_change_4h", "price_change_24h",
        "price_vs_sma20", "price_vs_sma50", "price_vs_sma200",
        "sma_slope_20", "sma_slope_50",
        "rsi_14", "rsi_divergence",
        "macd_value", "macd_signal_divergence",
    ]

    # 波动率类 (8维)
    VOLATILITY_FEATURES = [
        "atr_pct", "atr_percentile",
        "bollinger_width", "bollinger_position",
        "daily_range_pct", "weekly_range_pct",
        "volatility_regime", "realized_vol_30d",
    ]

    # 成交量类 (8维)
    VOLUME_FEATURES = [
        "volume_change_1h", "volume_vs_ma_20",
        "volume_price_trend", "obv_divergence",
        "vwap_deviation", "large_trade_ratio",
        "buy_volume_ratio", "volume_regime",
    ]

    # OI 衍生 (10维)
    OI_FEATURES = [
        "oi_change_pct", "oi_price_divergence",
        "long_short_ratio", "ls_ratio_change",
        "oi_large_trader", "funding_rate",
        "futures_basis_pct", "basis_regime",
        "oi_open_interest_pct", "oi_whale_activity",
    ]

    # 情绪 & 宏观 (8维)
    SENTIMENT_FEATURES = [
        "fear_greed_value", "fear_greed_class_encoded",
        "fear_greed_change", "fear_regime",
        "btc_dominance", "total_market_cap_change",
        "stablecoin_flow", "exchange_inflow",
    ]

    # 市场微观结构 (8维)
    MICRO_FEATURES = [
        "spread_pct", "spread_regime",
        "orderbook_imbalance", "depth_ratio",
        "tick_rule", "trade_size_regime",
        "quote_activity", "cancel_rate",
    ]

    @classmethod
    def all_feature_names(cls) -> list[str]:
        """返回所有 54 维特征名"""
        return (
            cls.MOMENTUM_FEATURES +
            cls.VOLATILITY_FEATURES +
            cls.VOLUME_FEATURES +
            cls.OI_FEATURES +
            cls.SENTIMENT_FEATURES +
            cls.MICRO_FEATURES
        )

    @classmethod
    def extract_basic(cls, ohlcv_data: list[dict]) -> dict[str, float]:
        """从 OHLCV 数据提取基础 23 维特征"""
        if len(ohlcv_data) < 50:
            return {}

        closes = np.array([c["close"] for c in ohlcv_data], dtype=np.float64)
        highs = np.array([c["high"] for c in ohlcv_data], dtype=np.float64)
        lows = np.array([c["low"] for c in ohlcv_data], dtype=np.float64)
        volumes = np.array([c["volume"] for c in ohlcv_data], dtype=np.float64)

        features = {}
        current_price = closes[-1]

        # --- 动量类 ---
        if len(closes) >= 2:
            features["price_change_1h"] = float((closes[-1] / closes[-2] - 1) * 100)
        if len(closes) >= 5:
            features["price_change_4h"] = float((closes[-1] / closes[-5] - 1) * 100)
        if len(closes) >= 24:
            features["price_change_24h"] = float((closes[-1] / closes[-24] - 1) * 100)

        sma20 = np.mean(closes[-20:]) if len(closes) >= 20 else current_price
        sma50 = np.mean(closes[-50:]) if len(closes) >= 50 else current_price
        sma200 = np.mean(closes) if len(closes) >= 200 else current_price

        features["price_vs_sma20"] = float((current_price / sma20 - 1) * 100)
        features["price_vs_sma50"] = float((current_price / sma50 - 1) * 100)
        features["price_vs_sma200"] = float((current_price / sma200 - 1) * 100)

        # SMA 斜率
        if len(closes) >= 20:
            sma20_series = np.convolve(closes[-30:], np.ones(20)/20, mode='valid')
            features["sma_slope_20"] = float(sma20_series[-1] / sma20_series[-5] - 1) * 100 if len(sma20_series) >= 5 else 0
        if len(closes) >= 50:
            sma50_series = np.convolve(closes[-60:], np.ones(50)/50, mode='valid')
            features["sma_slope_50"] = float(sma50_series[-1] / sma50_series[-5] - 1) * 100 if len(sma50_series) >= 5 else 0

        # RSI
        features["rsi_14"] = cls._compute_rsi(closes, 14)
        features["rsi_divergence"] = cls._rsi_divergence(closes)

        # MACD
        macd_val, signal_val = cls._compute_macd(closes)
        features["macd_value"] = macd_val
        features["macd_signal_divergence"] = macd_val - signal_val

        # --- 波动率类 ---
        features["atr_pct"] = cls._compute_atr_pct(highs, lows, closes, 14)
        features["atr_percentile"] = cls._atr_percentile(highs, lows, closes, 14)
        features["bollinger_width"] = cls._bollinger_width(closes, 20)
        features["bollinger_position"] = cls._bollinger_position(closes, 20)
        features["daily_range_pct"] = float(((highs[-1] / lows[-1]) - 1) * 100)
        if len(highs) >= 7:
            features["weekly_range_pct"] = float(((max(highs[-7:]) / min(lows[-7:])) - 1) * 100)
        features["volatility_regime"] = cls._volatility_regime(closes, 20)
        features["realized_vol_30d"] = float(np.std(np.diff(np.log(closes[-30:]))) * math.sqrt(365) * 100)

        # --- 成交量类 ---
        features["volume_change_1h"] = float((volumes[-1] / volumes[-2] - 1) * 100) if len(volumes) >= 2 else 0
        vol_ma20 = np.mean(volumes[-20:])
        vol_ratio = float((volumes[-1] / vol_ma20 - 1) * 100) if vol_ma20 > 0 else 0
        features["volume_vs_ma_20"] = vol_ratio
        features["volume_price_trend"] = cls._vpt(closes, volumes)
        features["obv_divergence"] = cls._obv_divergence(closes, volumes)
        features["vwap_deviation"] = cls._vwap_deviation(closes, highs, lows, volumes)
        features["large_trade_ratio"] = 0.0  # 需要逐笔成交流水（OKX 大单数据），暂不可从 OHLCV 推得
        # 主动买入量代理：近 20 根「上涨 K 线成交量」占比
        up_vol = sum(volumes[i] for i in range(-20, 0) if i - 1 >= -len(closes) and closes[i] > closes[i - 1])
        tot_vol = float(np.sum(volumes[-20:]))
        features["buy_volume_ratio"] = float(up_vol / tot_vol) if tot_vol > 0 else 0.5
        # 成交量状态：>1.5 倍均量=放量(+1)、<0.5 倍=缩量(-1)、否则 0
        features["volume_regime"] = 1.0 if vol_ratio > 50 else (-1.0 if vol_ratio < -50 else 0.0)

        return features

    @classmethod
    def extend_with_oi(cls, features: dict[str, float], oi_data: Optional[OpenInterestData]) -> dict[str, float]:
        """注入 OI 衍生特征 (10维)"""
        if oi_data is None:
            for key in cls.OI_FEATURES:
                features.setdefault(key, 0.0)
            return features

        features["oi_change_pct"] = oi_data.oi_change_24h_pct

        # OI-价格背离：价格涨 + OI 跌 = 看空背离
        price_change = features.get("price_change_24h", 0)
        features["oi_price_divergence"] = (price_change * -oi_data.oi_change_24h_pct) / 100

        features["long_short_ratio"] = oi_data.long_short_ratio
        features["ls_ratio_change"] = oi_data.ls_ratio_change_pct
        features["oi_large_trader"] = 0.0  # 需要更多粒度数据
        features["funding_rate"] = oi_data.funding_rate          # v2.1: 真实资金费率
        features["futures_basis_pct"] = oi_data.futures_basis_pct  # v2.1: 真实基差
        features["basis_regime"] = 1.0 if oi_data.futures_basis_pct > 0.5 else (-1.0 if oi_data.futures_basis_pct < -0.5 else 0.0)
        features["oi_open_interest_pct"] = oi_data.oi_change_1h_pct
        features["oi_whale_activity"] = 0.0

        return features

    @classmethod
    def extend_with_sentiment(cls, features: dict[str, float], fg_data: Optional[FearGreedData]) -> dict[str, float]:
        """注入情绪 & 宏观特征 (8维)"""
        if fg_data is None:
            for key in cls.SENTIMENT_FEATURES:
                features.setdefault(key, 0.0)
            return features

        features["fear_greed_value"] = float(fg_data.value)
        # 分类编码：extreme_fear=0, fear=1, neutral=2, greed=3, extreme_greed=4
        class_map = {"extreme_fear": 0, "fear": 1, "neutral": 2, "greed": 3, "extreme_greed": 4}
        features["fear_greed_class_encoded"] = float(class_map.get(fg_data.classification, 2))
        features["fear_greed_change"] = float(fg_data.value_change_1d)

        # Fear regime: 0=extreme_fear, 1=fear, 2=其他
        if fg_data.value <= 25:
            features["fear_regime"] = 0.0
        elif fg_data.value <= 45:
            features["fear_regime"] = 1.0
        else:
            features["fear_regime"] = 2.0

        features["btc_dominance"] = 0.0
        features["total_market_cap_change"] = 0.0
        features["stablecoin_flow"] = 0.0
        features["exchange_inflow"] = 0.0

        return features

    @classmethod
    def extend_micro(cls, features: dict[str, float], orderbook: Optional[dict] = None) -> dict[str, float]:
        """注入市场微观结构特征 (8维)"""
        for key in cls.MICRO_FEATURES:
            features.setdefault(key, 0.0)

        if orderbook:
            bids = orderbook.get("bids", [])
            asks = orderbook.get("asks", [])
            if bids and asks:
                best_bid = float(bids[0][0])
                best_ask = float(asks[0][0])
                mid = (best_bid + best_ask) / 2
                features["spread_pct"] = float((best_ask / best_bid - 1) * 100) if best_bid > 0 else 0

                bid_vol = sum(float(b[1]) for b in bids[:5])
                ask_vol = sum(float(a[1]) for a in asks[:5])
                total_vol = bid_vol + ask_vol
                features["orderbook_imbalance"] = float((bid_vol - ask_vol) / total_vol) if total_vol > 0 else 0
                features["depth_ratio"] = float(bid_vol / ask_vol) if ask_vol > 0 else 1.0

        return features

    # ------------------------------------------------------------------
    # 技术指标计算 (静态方法)
    # ------------------------------------------------------------------

    @staticmethod
    def _compute_rsi(closes: np.ndarray, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 50.0
        deltas = np.diff(closes[-(period + 1):])
        gains = np.maximum(deltas, 0)
        losses = np.maximum(-deltas, 0)
        avg_gain = np.mean(gains)
        avg_loss = np.mean(losses)
        if avg_loss == 0:
            return 100.0
        rs = avg_gain / avg_loss
        return float(100 - 100 / (1 + rs))

    @staticmethod
    def _rsi_divergence(closes: np.ndarray) -> float:
        return 0.0  # 简化为占位，完整版需价格与 RSI 背离检测

    @staticmethod
    def _ema_series(values: np.ndarray, period: int) -> np.ndarray:
        """EMA 序列（adjust=False）"""
        alpha = 2.0 / (period + 1.0)
        ema = np.empty_like(values, dtype=np.float64)
        ema[0] = values[0]
        for i in range(1, len(values)):
            ema[i] = values[i] * alpha + ema[i - 1] * (1 - alpha)
        return ema

    @staticmethod
    def _compute_macd(closes: np.ndarray) -> tuple[float, float]:
        """MACD(12,26,9) — 修复原 signal==macd 的恒等 bug"""
        if len(closes) < 26 + 9:
            return 0.0, 0.0
        ema12 = FeatureHub._ema_series(closes, 12)
        ema26 = FeatureHub._ema_series(closes, 26)
        macd_line = ema12 - ema26
        signal_line = FeatureHub._ema_series(macd_line, 9)
        return float(macd_line[-1]), float(signal_line[-1])

    @staticmethod
    def _compute_atr_pct(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
        if len(closes) < period + 1:
            return 0.0
        trs = []
        for i in range(1, min(len(closes), period + 1)):
            tr = max(
                highs[-i] - lows[-i],
                abs(highs[-i] - closes[-(i+1)]),
                abs(lows[-i] - closes[-(i+1)]),
            )
            trs.append(tr)
        atr = sum(trs) / len(trs) if trs else 0
        return float((atr / closes[-1]) * 100) if closes[-1] > 0 else 0.0

    @staticmethod
    def _atr_percentile(highs: np.ndarray, lows: np.ndarray, closes: np.ndarray, period: int = 14) -> float:
        return 0.5  # 占位：需要历史 ATR 序列计算分位

    @staticmethod
    def _bollinger_width(closes: np.ndarray, period: int = 20) -> float:
        if len(closes) < period:
            return 0.0
        window = closes[-period:]
        sma = np.mean(window)
        std = np.std(window)
        return float((sma + 2 * std) / (sma - 2 * std) - 1) if sma > 2 * std else 0.0

    @staticmethod
    def _bollinger_position(closes: np.ndarray, period: int = 20) -> float:
        if len(closes) < period:
            return 0.5
        window = closes[-period:]
        sma = np.mean(window)
        std = np.std(window)
        upper = sma + 2 * std
        lower = sma - 2 * std
        if upper == lower:
            return 0.5
        return float((closes[-1] - lower) / (upper - lower))

    @staticmethod
    def _volatility_regime(closes: np.ndarray, window: int = 20) -> float:
        if len(closes) < window * 2:
            return 1.0
        recent_vol = np.std(np.diff(np.log(closes[-window:])))
        past_vol = np.std(np.diff(np.log(closes[-2*window:-window])))
        if past_vol == 0:
            return 1.0
        ratio = recent_vol / past_vol
        # >1.5=高波动, <0.5=低波动
        return float(min(max((ratio - 0.5) / 1.0, 0), 1)) if ratio > 0 else 0.5

    @staticmethod
    def _vpt(closes: np.ndarray, volumes: np.ndarray) -> float:
        """Volume Price Trend 近5根变化率"""
        if len(closes) < 6 or len(volumes) < 6:
            return 0.0
        vpt = 0.0
        for i in range(-5, 0):
            change = (closes[i] / closes[i-1] - 1) if closes[i-1] > 0 else 0
            vpt += volumes[i] * change
        return float(vpt / volumes[-1]) if volumes[-1] > 0 else 0.0

    @staticmethod
    def _obv_divergence(closes: np.ndarray, volumes: np.ndarray) -> float:
        """OBV 与价格的方向一致性"""
        if len(closes) < 5:
            return 0.0
        obv_change = 0
        for i in range(-5, 0):
            if closes[i] > closes[i-1]:
                obv_change += volumes[i]
            elif closes[i] < closes[i-1]:
                obv_change -= volumes[i]
        price_change = closes[-1] - closes[-5]
        return 1.0 if (obv_change > 0) == (price_change > 0) else -1.0

    @staticmethod
    def _vwap_deviation(closes: np.ndarray, highs: np.ndarray, lows: np.ndarray, volumes: np.ndarray) -> float:
        if len(closes) < 20 or volumes[-20:].sum() == 0:
            return 0.0
        typical = (highs[-20:] + lows[-20:] + closes[-20:]) / 3
        vwap = np.sum(typical * volumes[-20:]) / np.sum(volumes[-20:])
        return float((closes[-1] / vwap - 1) * 100) if vwap > 0 else 0.0


# ------------------------------------------------------------------
# PCA 降维
# ------------------------------------------------------------------


class PCAReducer:
    """PCA 降维，保留 95% 方差"""

    def __init__(self, target_variance: float = 0.95):
        self.target_variance = target_variance
        self._n_components: int = 0
        self._explained_variance: float = 0.0
        self._mean: Optional[np.ndarray] = None
        self._components: Optional[np.ndarray] = None

    def fit_transform(self, features: np.ndarray) -> tuple[np.ndarray, int, float]:
        """
        对特征矩阵做 PCA 降维
        features: shape (n_samples, n_features)
        返回: (transformed, n_components, explained_variance)
        """
        if features.size == 0 or features.ndim != 2:
            return np.array([[]]), 0, 0.0

        n_samples, n_features = features.shape
        if n_samples < 2 or n_features < 2:
            return features, n_features, 1.0

        # 中心化
        self._mean = np.mean(features, axis=0)
        centered = features - self._mean

        # 协方差矩阵
        cov = np.cov(centered, rowvar=False)
        eigenvalues, eigenvectors = np.linalg.eigh(cov)

        # 降序排列
        idx = np.argsort(eigenvalues)[::-1]
        eigenvalues = eigenvalues[idx]
        eigenvectors = eigenvectors[:, idx]

        # 累积方差
        total_var = np.sum(eigenvalues)
        cumsum = np.cumsum(eigenvalues) / total_var if total_var > 0 else np.zeros_like(eigenvalues)

        # 找满足 target_variance 的最小主成分数
        self._n_components = int(np.searchsorted(cumsum, self.target_variance) + 1)
        self._n_components = min(self._n_components, n_features)
        self._explained_variance = float(cumsum[self._n_components - 1]) if self._n_components > 0 else 0.0

        self._components = eigenvectors[:, :self._n_components]
        transformed = np.dot(centered, self._components)

        return transformed, self._n_components, self._explained_variance

    def transform(self, features: np.ndarray) -> np.ndarray:
        """用已训练的 PCA 变换新数据"""
        if self._mean is None or self._components is None:
            return features
        centered = features - self._mean
        return np.dot(centered, self._components)


# ------------------------------------------------------------------
# WeakSignalEngine — 主引擎
# ------------------------------------------------------------------


class WeakSignalEngine:
    """弱信号矩阵引擎：多源数据融合 → 特征扩展 → PCA 降维"""

    CACHE_TTL: float = 600.0  # 10分钟

    def __init__(self):
        self._cache: dict[str, tuple[float, SignalMatrixResult]] = {}
        self._pca = PCAReducer()
        self._feature_history: list[np.ndarray] = []  # 累积历史用于 PCA

    def compute(
        self,
        ohlcv_data: list[dict],
        symbol: str = "BTC/USDT",
        oi_data: Optional[OpenInterestData] = None,
        fg_data: Optional[FearGreedData] = None,
        orderbook: Optional[dict] = None,
    ) -> SignalMatrixResult:
        """计算弱信号矩阵"""
        if not ohlcv_data or len(ohlcv_data) < 50:
            log.warning(f"WeakSignalEngine[{symbol}]: insufficient OHLCV data")
            return self._empty_result(symbol)

        # 缓存
        cache_key = f"{symbol}:{len(ohlcv_data)}"
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached[0] < self.CACHE_TTL:
            return cached[1]

        # 1) 基础特征提取
        features = FeatureHub.extract_basic(ohlcv_data)
        base_count = len(features)

        # 2) OI 特征注入
        features = FeatureHub.extend_with_oi(features, oi_data)

        # 3) 情绪特征注入
        features = FeatureHub.extend_with_sentiment(features, fg_data)

        # 4) 微观结构注入
        features = FeatureHub.extend_micro(features, orderbook)

        feature_count_total = len(features)

        # 5) 筛选有效特征（非 NaN, 非 Inf, 有方差）
        feature_names = sorted(features.keys())
        feature_values = np.array([features.get(k, 0.0) for k in feature_names], dtype=np.float64)
        valid_mask = np.isfinite(feature_values)
        selected = feature_values[valid_mask]
        feature_count_selected = int(np.sum(valid_mask))

        # 6) PCA 降维
        self._feature_history.append(selected.reshape(1, -1))
        if len(self._feature_history) > 100:
            self._feature_history = self._feature_history[-100:]

        pca_components = 0
        pca_var = 0.0
        pc_list: list[list[float]] = []

        if len(self._feature_history) >= 10:
            history_matrix = np.vstack(self._feature_history)
            transformed, pca_components, pca_var = self._pca.fit_transform(history_matrix)
            if transformed.size > 0:
                last_row = transformed[-1, :].tolist()
                pc_list = [last_row]
        else:
            # 不足 10 个样本时直接用原始特征
            pc_list = [selected.tolist()]
            pca_components = feature_count_selected
            pca_var = 1.0

        result = SignalMatrixResult(
            symbol=symbol,
            feature_count_total=feature_count_total,
            feature_count_selected=feature_count_selected,
            pca_n_components=pca_components,
            pca_explained_variance=pca_var,
            principal_components=pc_list,
            oi_data=oi_data,
            fear_greed=fg_data,
        )

        self._cache[cache_key] = (time.time(), result)
        log.info(f"WeakSignalEngine[{symbol}]: {feature_count_selected}/{feature_count_total} features → "
                 f"{pca_components} PCs ({pca_var:.2%} var)")
        return result

    def clear_cache(self):
        self._cache.clear()

    @staticmethod
    def _empty_result(symbol: str) -> SignalMatrixResult:
        return SignalMatrixResult(
            symbol=symbol,
            feature_count_total=0,
            feature_count_selected=0,
            pca_n_components=0,
            pca_explained_variance=0.0,
            principal_components=[],
        )


# 全局单例
weak_signal_engine = WeakSignalEngine()
