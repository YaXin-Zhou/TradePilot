"""因子 IC/ICIR 检验 — 评估技术因子对前瞻收益的预测能力

IC (Information Coefficient) = 因子值与前瞻收益的 Spearman 秩相关（-1 ~ +1）
ICIR = 多个子周期 IC 的均值 / 标准差（衡量 IC 的稳定性，> 0.3 通常视为有效）

用途（V3 B2）：对真实因子做 IC 检验，筛选 |IC| 显著且 ICIR 稳定的因子后再喂 ML。
"""
from __future__ import annotations

import numpy as np
from scipy.stats import spearmanr


def forward_returns(closes, horizon: int = 1) -> np.ndarray:
    """前瞻收益：close[t+horizon]/close[t] - 1（最后 horizon 根为 NaN）"""
    closes = np.asarray(closes, dtype=np.float64)
    rets = np.full(len(closes), np.nan)
    rets[:-horizon] = closes[horizon:] / closes[:-horizon] - 1.0
    return rets


def compute_ic(factor, returns) -> float:
    """单因子 IC = Spearman 秩相关（要求至少 20 个有效样本）"""
    f = np.asarray(factor, dtype=np.float64)
    r = np.asarray(returns, dtype=np.float64)
    mask = np.isfinite(f) & np.isfinite(r)
    if mask.sum() < 20:
        return float("nan")
    corr = spearmanr(f[mask], r[mask]).correlation
    return float(corr) if corr is not None and np.isfinite(corr) else float("nan")


def compute_icir(factor, returns, n_periods: int = 10) -> float:
    """ICIR = 各子周期 IC 的均值 / 标准差（衡量 IC 稳定性）"""
    f = np.asarray(factor, dtype=np.float64)
    r = np.asarray(returns, dtype=np.float64)
    mask = np.isfinite(f) & np.isfinite(r)
    f, r = f[mask], r[mask]
    n = len(f)
    if n < n_periods * 20:
        return float("nan")
    period_len = n // n_periods
    ics = []
    for i in range(n_periods):
        sl = slice(i * period_len, (i + 1) * period_len)
        ic = compute_ic(f[sl], r[sl])
        if np.isfinite(ic):
            ics.append(ic)
    if len(ics) < 3:
        return float("nan")
    ics = np.asarray(ics, dtype=np.float64)
    std = ics.std()
    return float(ics.mean() / std) if std > 0 else 0.0


def analyze_ohlcv_factors(ohlcv_data: list[dict], horizon: int = 1) -> dict:
    """对 OHLCV 可计算的因子做 IC/ICIR 检验。

    返回 {因子名: {"ic": float|None, "icir": float|None}}。
    只包含可从 OHLCV 直接计算的因子（OI/资金费率等外部因子需另接历史数据）。
    """
    import pandas as pd

    if not ohlcv_data or len(ohlcv_data) < 80:
        return {}

    df = pd.DataFrame(ohlcv_data).sort_values("timestamp").reset_index(drop=True)
    close = df["close"]
    rets = forward_returns(close.values, horizon)

    factors: dict[str, np.ndarray] = {}

    # RSI(14) — Wilder
    delta = close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    factors["rsi_14"] = (100 - 100 / (1 + rs)).values

    # price_vs_sma20 (%)
    sma20 = close.rolling(20).mean()
    factors["price_vs_sma20"] = ((close / sma20 - 1) * 100).values

    # price_vs_sma50 (%)
    sma50 = close.rolling(50).mean()
    factors["price_vs_sma50"] = ((close / sma50 - 1) * 100).values

    # macd_hist (MACD 12/26/9)
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    macd = ema12 - ema26
    signal = macd.ewm(span=9, adjust=False).mean()
    factors["macd_hist"] = (macd - signal).values

    # volume_ratio (相对 20 根均量)
    vol_ma20 = df["volume"].rolling(20).mean()
    factors["volume_ratio"] = (df["volume"] / vol_ma20.replace(0, np.nan)).values

    # realized_vol_30 (年化 %)
    log_ret = np.log(close).diff()
    factors["realized_vol_30"] = (log_ret.rolling(30).std() * np.sqrt(365) * 100).values

    # bollinger_position
    sma = close.rolling(20).mean()
    std = close.rolling(20).std()
    upper = sma + 2 * std
    lower = sma - 2 * std
    factors["bollinger_position"] = ((close - lower) / (upper - lower).replace(0, np.nan)).values

    report = {}
    for name, series in factors.items():
        ic = compute_ic(series, rets)
        icir = compute_icir(series, rets)
        report[name] = {
            "ic": round(ic, 4) if np.isfinite(ic) else None,
            "icir": round(icir, 4) if np.isfinite(icir) else None,
        }
    return report
