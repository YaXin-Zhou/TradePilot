"""
市场状态检测器 — 基于 MA 斜率 + ATR 波动率的四状态分类

States:
  TRENDING_UP    — MA 斜率 > 0.5% + 波动率任意
  TRENDING_DOWN  — MA 斜率 < -0.5% + 波动率任意
  RANGING_HIGH_VOL — |MA 斜率| <= 0.5% + ATR% > 中位数
  RANGING_LOW_VOL  — |MA 斜率| <= 0.5% + ATR% <= 中位数

Cache: 5 分钟 TTL，避免重复计算
"""
from __future__ import annotations

import time
import math
from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from core.logger import log


class MarketRegime(str, Enum):
    TRENDING_UP = "TRENDING_UP"
    TRENDING_DOWN = "TRENDING_DOWN"
    RANGING_HIGH_VOL = "RANGING_HIGH_VOL"
    RANGING_LOW_VOL = "RANGING_LOW_VOL"


@dataclass
class RegimeResult:
    regime: MarketRegime
    confidence: float          # 0.0 ~ 1.0
    ma_slope_pct: float        # MA50 斜率 (%)
    atr_pct: float             # ATR / 价格 (%)
    atr_median_pct: float      # 历史 ATR 中位数 (%)
    volatility_percentile: float  # 当前波动率在历史中的分位数
    price: float
    timestamp: float = field(default_factory=time.time)

    def to_dict(self) -> dict:
        return {
            "regime": self.regime.value,
            "confidence": round(self.confidence, 3),
            "ma_slope_pct": round(self.ma_slope_pct, 4),
            "atr_pct": round(self.atr_pct, 4),
            "atr_median_pct": round(self.atr_median_pct, 4),
            "volatility_percentile": round(self.volatility_percentile, 3),
            "price": self.price,
            "timestamp": self.timestamp,
        }


class RegimeDetector:
    """市场状态检测器"""

    # 配置常量
    MA_PERIOD: int = 50
    ATR_PERIOD: int = 14
    SLOPE_THRESHOLD: float = 0.5      # 0.5% 斜率阈值
    CACHE_TTL: float = 300.0          # 5 分钟缓存

    def __init__(self):
        self._cache: dict[str, tuple[float, RegimeResult]] = {}

    # ------------------------------------------------------------------
    # 公开方法
    # ------------------------------------------------------------------

    def detect(self, ohlcv_data: list[dict], symbol: str = "BTC/USDT") -> RegimeResult:
        """从 OHLCV 数据检测市场状态"""
        if not ohlcv_data or len(ohlcv_data) < self.MA_PERIOD:
            log.warning(f"RegimeDetector: insufficient data ({len(ohlcv_data)} < {self.MA_PERIOD})")
            return self._default_result(symbol)

        # 检查缓存
        cache_key = f"{symbol}:{len(ohlcv_data)}"
        cached = self._cache.get(cache_key)
        if cached and time.time() - cached[0] < self.CACHE_TTL:
            return cached[1]

        closes = [c["close"] for c in ohlcv_data]
        highs = [c["high"] for c in ohlcv_data]
        lows = [c["low"] for c in ohlcv_data]

        # 1) MA50 斜率
        ma50 = self._sma(closes, self.MA_PERIOD)
        if ma50 is None:
            return self._default_result(symbol)
        ma_slope_pct = (ma50[-1] - ma50[0]) / ma50[0] * 100

        # 2) ATR 波动率
        atr_values = self._compute_atr(highs, lows, closes, self.ATR_PERIOD)
        current_atr_pct = (atr_values[-1] / closes[-1]) * 100 if atr_values else 0

        # 3) 历史 ATR 分位数
        all_atr_pct = [v / closes[i] * 100 for i, v in enumerate(atr_values) if closes[i] > 0]
        atr_median = sorted(all_atr_pct)[len(all_atr_pct) // 2] if all_atr_pct else current_atr_pct
        vol_percentile = sum(1 for v in all_atr_pct if v <= current_atr_pct) / max(len(all_atr_pct), 1)

        # 4) 分类
        regime, confidence = self._classify(ma_slope_pct, current_atr_pct, atr_median, vol_percentile)

        result = RegimeResult(
            regime=regime,
            confidence=confidence,
            ma_slope_pct=ma_slope_pct,
            atr_pct=current_atr_pct,
            atr_median_pct=atr_median,
            volatility_percentile=vol_percentile,
            price=closes[-1],
        )

        self._cache[cache_key] = (time.time(), result)
        log.info(f"RegimeDetector[{symbol}]: {regime.value} conf={confidence:.2f} "
                 f"slope={ma_slope_pct:.3f}% atr={current_atr_pct:.3f}%")
        return result

    def clear_cache(self):
        self._cache.clear()

    # ------------------------------------------------------------------
    # 内部分类逻辑
    # ------------------------------------------------------------------

    def _classify(self, slope: float, atr: float, atr_median: float,
                  vol_percentile: float) -> tuple[MarketRegime, float]:
        """根据斜率和波动率分类，返回 (regime, confidence)"""
        is_high_vol = atr > atr_median

        if slope > self.SLOPE_THRESHOLD:
            # 趋势上涨 — 置信度基于斜率强度 + 波动率方向
            conf = min(1.0, (slope / 0.02) * 0.7 + (0.5 if is_high_vol else 0.3))
            return MarketRegime.TRENDING_UP, round(conf, 3)
        elif slope < -self.SLOPE_THRESHOLD:
            abs_slope = abs(slope)
            conf = min(1.0, (abs_slope / 0.02) * 0.7 + (0.5 if is_high_vol else 0.3))
            return MarketRegime.TRENDING_DOWN, round(conf, 3)
        else:
            if is_high_vol:
                conf = min(1.0, vol_percentile)
                return MarketRegime.RANGING_HIGH_VOL, round(conf, 3)
            else:
                conf = max(0.3, 1.0 - vol_percentile)
                return MarketRegime.RANGING_LOW_VOL, round(conf, 3)

    # ------------------------------------------------------------------
    # 技术指标
    # ------------------------------------------------------------------

    @staticmethod
    def _sma(data: list[float], period: int) -> Optional[list[float]]:
        if len(data) < period:
            return None
        result = []
        window_sum = sum(data[:period])
        result.append(window_sum / period)
        for i in range(period, len(data)):
            window_sum += data[i] - data[i - period]
            result.append(window_sum / period)
        return result

    @staticmethod
    def _compute_atr(highs: list[float], lows: list[float], closes: list[float],
                     period: int) -> list[float]:
        """计算 ATR 序列"""
        tr_list = []
        for i in range(1, len(closes)):
            tr = max(
                highs[i] - lows[i],
                abs(highs[i] - closes[i - 1]),
                abs(lows[i] - closes[i - 1]),
            )
            tr_list.append(tr)

        if len(tr_list) < period:
            return [sum(tr_list) / len(tr_list)] if tr_list else [0]

        atr = [sum(tr_list[:period]) / period]
        for i in range(period, len(tr_list)):
            atr.append((atr[-1] * (period - 1) + tr_list[i]) / period)
        return atr

    @staticmethod
    def _default_result(symbol: str) -> RegimeResult:
        return RegimeResult(
            regime=MarketRegime.RANGING_LOW_VOL,
            confidence=0.0,
            ma_slope_pct=0.0,
            atr_pct=0.0,
            atr_median_pct=0.0,
            volatility_percentile=0.5,
            price=0.0,
        )


# 全局单例
regime_detector = RegimeDetector()
