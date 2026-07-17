"""特征工程 - 技术指标计算"""
import pandas as pd
import numpy as np
import pandas_ta as ta
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

    def compute_features(self, df: pd.DataFrame) -> pd.DataFrame:
        """对 OHLCV DataFrame 计算技术指标特征"""
        if df.empty or len(df) < 50:
            return df

        df = df.copy().sort_values("timestamp")

        # --- 趋势指标 ---
        # EMA
        df["ema_9"] = ta.ema(df["close"], length=9)
        df["ema_21"] = ta.ema(df["close"], length=21)
        df["ema_50"] = ta.ema(df["close"], length=50)

        # SMA
        df["sma_20"] = ta.sma(df["close"], length=20)
        df["sma_50"] = ta.sma(df["close"], length=50)
        df["sma_200"] = ta.sma(df["close"], length=200)

        # MACD
        macd = ta.macd(df["close"])
        if macd is not None:
            df["macd"] = macd.get("MACD_12_26_9", np.nan)
            df["macd_signal"] = macd.get("MACDs_12_26_9", np.nan)
            df["macd_hist"] = macd.get("MACDh_12_26_9", np.nan)

        # --- 震荡指标 ---
        # RSI
        rsi = ta.rsi(df["close"], length=14)
        df["rsi_14"] = rsi

        # 布林带
        bb = ta.bbands(df["close"], length=20)
        if bb is not None:
            df["bb_upper"] = bb.get("BBU_20_2.0", np.nan)
            df["bb_lower"] = bb.get("BBL_20_2.0", np.nan)
            df["bb_width"] = (df["bb_upper"] - df["bb_lower"]) / df["bb_lower"]
            df["bb_pct"] = (df["close"] - df["bb_lower"]) / (df["bb_upper"] - df["bb_lower"])

        # --- 量价指标 ---
        # ATR
        df["atr_14"] = ta.atr(df["high"], df["low"], df["close"], length=14)

        # OBV
        df["obv"] = ta.obv(df["close"], df["volume"])

        # VWAP
        df["vwap"] = (df["volume"] * (df["high"] + df["low"] + df["close"]) / 3).cumsum() / df["volume"].cumsum()

        # 成交量均线
        df["volume_sma_20"] = ta.sma(df["volume"], length=20)
        df["volume_ratio"] = df["volume"] / df["volume_sma_20"]

        # --- 价格变化率 ---
        df["close_pct_change_1"] = df["close"].pct_change(1)
        df["close_pct_change_5"] = df["close"].pct_change(5)
        df["close_pct_change_20"] = df["close"].pct_change(20)
        df["high_low_pct"] = (df["high"] - df["low"]) / df["close"]
        df["close_open_pct"] = (df["close"] - df["open"]) / df["open"]

        # 删除 NaN 行
        df = df.replace([np.inf, -np.inf], np.nan)
        df = df.dropna()
        return df

    def get_feature_columns(self) -> list:
        return self.DEFAULT_FEATURES
