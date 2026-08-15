"""特征工程 - 技术指标计算

v2.0: 移除 pandas-ta 依赖（该库 2022 年停更，与 pandas 2.x / Python 3.13 不兼容），
改为纯 pandas/numpy 自实现同等指标（EMA/SMA/MACD/RSI/BB/ATR/OBV）。
"""
import pandas as pd
import numpy as np
from typing import Optional


class FeatureEngine:
    """计算技术指标作为 ML 特征"""

    DEFAULT_FEATURES = [
        "rsi_14", "macd", "macd_signal", "macd_hist",
        "bb_upper", "bb_lower", "bb_width", "bb_pct",
        "ema_9", "ema_21", "ema_50",
        "sma_20", "sma_50", "sma_200",
        "atr_14", "obv", "vwap",
        "volume_sma_20", "volume_ratio",
        "close_pct_change_1", "close_pct_change_5", "close_pct_change_20",
        "high_low_pct", "close_open_pct",
    ]

    @staticmethod
    def _ema(series: pd.Series, length: int) -> pd.Series:
        return series.ewm(span=length, adjust=False).mean()

    @staticmethod
    def _rsi(close: pd.Series, length: int = 14) -> pd.Series:
        """Wilder's RSI（与 pandas-ta 默认一致）"""
        delta = close.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(alpha=1 / length, adjust=False).mean()
        avg_loss = loss.ewm(alpha=1 / length, adjust=False).mean()
        rs = avg_gain / avg_loss.replace(0, np.nan)
        return 100 - 100 / (1 + rs)

    @staticmethod
    def _atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int = 14) -> pd.Series:
        """Wilder's ATR"""
        prev_close = close.shift(1)
        tr = pd.concat(
            [
                high - low,
                (high - prev_close).abs(),
                (low - prev_close).abs(),
            ],
            axis=1,
        ).max(axis=1)
        return tr.ewm(alpha=1 / length, adjust=False).mean()

    def compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """对 OHLCV DataFrame 计算技术指标特征"""
        if df.empty or len(df) < 50:
            return df

        df = df.copy().sort_values("timestamp")
        close = df["close"]
        high = df["high"]
        low = df["low"]
        volume = df["volume"]

        # --- 趋势指标 ---
        df["ema_9"] = self._ema(close, 9)
        df["ema_21"] = self._ema(close, 21)
        df["ema_50"] = self._ema(close, 50)

        df["sma_20"] = close.rolling(20).mean()
        df["sma_50"] = close.rolling(50).mean()
        df["sma_200"] = close.rolling(200).mean()

        # MACD（12/26/9）
        ema_12 = self._ema(close, 12)
        ema_26 = self._ema(close, 26)
        df["macd"] = ema_12 - ema_26
        df["macd_signal"] = df["macd"].ewm(span=9, adjust=False).mean()
        df["macd_hist"] = df["macd"] - df["macd_signal"]

        # --- 震荡指标 ---
        df["rsi_14"] = self._rsi(close, 14)

        # 布林带（20, 2.0）
        sma_20 = close.rolling(20).mean()
        std_20 = close.rolling(20).std(ddof=0)
        df["bb_upper"] = sma_20 + 2.0 * std_20
        df["bb_lower"] = sma_20 - 2.0 * std_20
        df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_lower"].replace(0, np.nan)
        df["bb_pct"] = (close - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"]).replace(0, np.nan)

        # --- 量价指标 ---
        df["atr_14"] = self._atr(high, low, close, 14)

        # OBV
        direction = np.sign(close.diff()).fillna(0)
        df["obv"] = (direction * volume).cumsum()

        # VWAP（累计典型价×量 / 累计量）
        typical_price = (high + low + close) / 3
        df["vwap"] = (typical_price * volume).cumsum() / volume.cumsum().replace(0, np.nan)

        df["volume_sma_20"] = volume.rolling(20).mean()
        df["volume_ratio"] = volume / df["volume_sma_20"].replace(0, np.nan)

        # --- 价格变化率 ---
        df["close_pct_change_1"] = close.pct_change(1)
        df["close_pct_change_5"] = close.pct_change(5)
        df["close_pct_change_20"] = close.pct_change(20)
        df["high_low_pct"] = (high - low) / close.replace(0, np.nan)
        df["close_open_pct"] = (close - df["open"]) / df["open"].replace(0, np.nan)

        # 只删除核心指标为 NaN 的行（SMA_200 等长周期指标允许 NaN）
        df = df.replace([np.inf, -np.inf], np.nan)
        core_cols = ["rsi_14", "macd", "close", "ema_9", "ema_21", "atr_14"]
        df = df.dropna(subset=[c for c in core_cols if c in df.columns])
        return df

    def get_feature_columns(self) -> list:
        return self.DEFAULT_FEATURES
