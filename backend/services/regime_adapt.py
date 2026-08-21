"""Regime 自适应权重 — v6 5.1（替代「AI 挖因子」）

核心思想：因子会随市场失效（alpha decay），但「regime = 趋势/震荡 × 高/低波动」
是稳定且可解释的自适应维度。本模块在固定 regime 分类上，按「策略类型 × regime
匹配度」调整权重：趋势市偏向趋势策略，震荡市偏向均值回归策略，高波动降总敞口。

固定小因子池（动量 / 波动率）已经由 regime_detector 压缩进 regime 分类，因此
这里不做额外因子计算，只做「regime → 策略权重」的映射，避免重回过拟合式挖因子。

fail-closed：当前 regime 下没有任何兼容策略时返回空权重（空仓），绝不为了
「保持有仓位」而强行分配。
"""
from __future__ import annotations

from services.regime_detector import MarketRegime

# 固定「策略类型 × regime」偏好表：值越大越适合该 regime（0 = 不兼容）
REGIME_PREFERENCE: dict[MarketRegime, dict[str, float]] = {
    MarketRegime.TRENDING_UP: {
        "ma_cross": 1.0, "sma_cross": 1.0, "grid": 0.0,
        "rsi": 0.2, "bollinger": 0.2, "ml_signal": 0.3,
        "custom": 0.5, "ai_generated": 0.5,
    },
    MarketRegime.TRENDING_DOWN: {
        "ma_cross": 1.0, "sma_cross": 1.0, "grid": 0.0,
        "rsi": 0.2, "bollinger": 0.2, "ml_signal": 0.3,
        "custom": 0.5, "ai_generated": 0.5,
    },
    MarketRegime.RANGING_LOW_VOL: {
        "ma_cross": 0.1, "sma_cross": 0.1, "grid": 0.8,
        "rsi": 1.0, "bollinger": 0.9, "ml_signal": 0.5,
        "custom": 0.5, "ai_generated": 0.5,
    },
    MarketRegime.RANGING_HIGH_VOL: {
        "ma_cross": 0.1, "sma_cross": 0.1, "grid": 0.5,
        "rsi": 0.4, "bollinger": 0.8, "ml_signal": 0.4,
        "custom": 0.4, "ai_generated": 0.4,
    },
}

# 高波动 regime 的整体敞口折扣（风控：震荡高波动少下注）
_EXPOSURE_SCALE: dict[MarketRegime, float] = {
    MarketRegime.TRENDING_UP: 1.0,
    MarketRegime.TRENDING_DOWN: 1.0,
    MarketRegime.RANGING_LOW_VOL: 1.0,
    MarketRegime.RANGING_HIGH_VOL: 0.5,
}


def strategy_multiplier(regime: MarketRegime, strategy_type: str) -> float:
    """返回该策略类型在当前 regime 下的权重乘数（0 = 不兼容，1.0 = 最匹配）。

    供 runner 对单策略权重做 regime 自适应：不兼容类型乘 0 → 不参与分配。
    """
    stype = (strategy_type or "").lower()
    pref = REGIME_PREFERENCE.get(regime, {})
    return pref.get(stype, 0.5)  # 未知类型给中性 0.5，偏保守


def adapt_weights(regime: MarketRegime, strategies: list[dict],
                  base_weights: dict[str, float] | None = None) -> dict[str, float]:
    """按 regime 调整多策略权重。返回 {strategy_id: weight}（已归一化）。

    strategies: [{strategy_id, strategy_type, ...}]
    base_weights: 可选，原始权重（缺省等权）。
    fail-closed：无兼容策略（所有乘数都 0）时返回 {}，调用方据此空仓。
    """
    raw: dict[str, float] = {}
    n = max(len(strategies), 1)
    for s in strategies:
        sid = s.get("strategy_id") or s.get("id")
        stype = (s.get("strategy_type") or s.get("type") or "").lower()
        if not sid:
            continue
        mult = strategy_multiplier(regime, stype)
        if mult <= 0:
            continue  # 该 regime 下不兼容，排除
        base = (base_weights or {}).get(sid, 1.0 / n)
        raw[sid] = base * mult

    if not raw:
        return {}  # fail-closed

    total = sum(raw.values())
    if total <= 0:
        return {}
    scale = _EXPOSURE_SCALE.get(regime, 1.0)
    return {sid: round(w / total * scale, 6) for sid, w in raw.items()}
