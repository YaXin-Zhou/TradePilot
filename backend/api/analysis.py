"""分析 API — 市场状态 / 风控策略 / 弱信号 / 情绪"""
import numpy as np
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from auth.deps import get_current_user
from services.market_service import get_ohlcv
from services.regime_detector import regime_detector
from services.risk_engine import risk_engine, RiskPolicy
from services.feature_engine import weak_signal_engine
from services.external_data import oi_fetcher, fear_greed_fetcher
from services.news_sentiment import get_news_sentiment_engine

router = APIRouter(prefix="/api/analysis", tags=["analysis"])


# ------------------------------------------------------------------
# Regime 检测
# ------------------------------------------------------------------

class RegimeResponse(BaseModel):
    success: bool = True
    data: dict | None = None
    error: str | None = None


@router.get("/market-regime")
def get_market_regime(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("1h"),
    _user: dict = Depends(get_current_user),
):
    """获取当前市场状态"""
    try:
        ohlcv, _ = get_ohlcv(symbol, timeframe, limit=200)
        result = regime_detector.detect(ohlcv, symbol)
        return {"success": True, "data": result.to_dict()}
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


# ------------------------------------------------------------------
# 风控策略管理
# ------------------------------------------------------------------

class UpdatePolicyRequest(BaseModel):
    regime: str
    max_position_pct: float | None = None
    max_single_strategy_pct: float | None = None
    max_daily_loss_pct: float | None = None
    stop_loss_pct: float | None = None
    trailing_stop_pct: float | None = None
    min_sharpe_entry: float | None = None
    max_correlation: float | None = None
    time_stop_hours: int | None = None
    atr_stop_multiplier: float | None = None
    allowed_strategies: list[str] | None = None


@router.get("/risk-policies")
def get_risk_policies(_user: dict = Depends(get_current_user)):
    """获取所有 Regime 的风控策略"""
    policies = risk_engine.get_all_policies()
    return {"success": True, "data": policies}


@router.post("/risk-policies")
def update_risk_policy(req: UpdatePolicyRequest, _user: dict = Depends(get_current_user)):
    """更新单个 Regime 的风控策略"""
    from services.regime_detector import MarketRegime
    try:
        regime = MarketRegime(req.regime.upper())
    except ValueError:
        return {"success": False, "error": f"Invalid regime: {req.regime}"}

    kwargs = {k: v for k, v in req.dict(exclude={"regime"}).items() if v is not None}
    policy = risk_engine.update_policy(regime, **kwargs)
    return {"success": True, "data": policy.to_dict()}


@router.post("/risk-policies/reset")
def reset_risk_policies(_user: dict = Depends(get_current_user)):
    """重置风控策略为默认值"""
    risk_engine.reset_to_defaults()
    return {"success": True, "data": risk_engine.get_all_policies()}


# ------------------------------------------------------------------
# 风控检查
# ------------------------------------------------------------------

class RiskCheckRequest(BaseModel):
    regime: str
    strategy_type: str
    sharpe_oos: float
    total_capital: float
    current_position: float = 0
    new_amount: float = 0
    strategy_position: float = 0
    daily_pnl: float = 0


@router.post("/risk-check")
def check_risk(req: RiskCheckRequest, _user: dict = Depends(get_current_user)):
    """执行风控检查"""
    from services.regime_detector import MarketRegime
    try:
        regime = MarketRegime(req.regime.upper())
    except ValueError:
        return {"success": False, "error": f"Invalid regime: {req.regime}"}

    result = risk_engine.full_check(
        regime=regime,
        strategy_type=req.strategy_type,
        sharpe_oos=req.sharpe_oos,
        total_capital=req.total_capital,
        current_position=req.current_position,
        new_amount=req.new_amount,
        strategy_position=req.strategy_position,
        daily_pnl=req.daily_pnl,
        user_id=_user.get("sub", "anonymous"),
    )
    return {"success": True, "data": result.to_dict()}


# ------------------------------------------------------------------
# 弱信号矩阵 (Weak Signal Matrix)
# ------------------------------------------------------------------

@router.get("/weak-signals")
async def get_weak_signals(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("1h"),
    _user: dict = Depends(get_current_user),
):
    """获取弱信号矩阵（多源数据 + PCA 降维）"""
    try:
        ohlcv, _ = get_ohlcv(symbol, timeframe, limit=200)

        # 并行获取外部数据
        oi_data = await oi_fetcher.fetch(symbol)
        fg_data = await fear_greed_fetcher.fetch()

        result = weak_signal_engine.compute(ohlcv, symbol, oi_data, fg_data)
        return {"success": True, "data": result.to_dict()}
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


@router.get("/feature-names")
def get_feature_names(_user: dict = Depends(get_current_user)):
    """获取所有 54 维弱信号特征名"""
    from services.feature_engine import FeatureHub
    all_names = FeatureHub.all_feature_names()
    return {
        "success": True,
        "data": {
            "total": len(all_names),
            "categories": {
                "momentum": FeatureHub.MOMENTUM_FEATURES,
                "volatility": FeatureHub.VOLATILITY_FEATURES,
                "volume": FeatureHub.VOLUME_FEATURES,
                "oi": FeatureHub.OI_FEATURES,
                "sentiment": FeatureHub.SENTIMENT_FEATURES,
                "micro": FeatureHub.MICRO_FEATURES,
            },
        },
    }


# ------------------------------------------------------------------
# 外部数据 (Fear & Greed + OI)
# ------------------------------------------------------------------

@router.get("/fear-greed")
async def get_fear_greed(_user: dict = Depends(get_current_user)):
    """获取恐惧贪婪指数"""
    try:
        data = await fear_greed_fetcher.fetch()
        if data:
            return {"success": True, "data": data.to_dict()}
        return {"success": False, "error": "Failed to fetch Fear & Greed Index", "data": None}
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


@router.get("/open-interest")
async def get_open_interest(
    symbol: str = Query("BTC/USDT"),
    _user: dict = Depends(get_current_user),
):
    """获取 OKX 持仓数据"""
    try:
        data = await oi_fetcher.fetch(symbol)
        if data:
            return {"success": True, "data": data.to_dict()}
        return {"success": False, "error": "Failed to fetch Open Interest", "data": None}
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


# ------------------------------------------------------------------
# 新闻情绪分析 (News Sentiment)
# ------------------------------------------------------------------

@router.get("/news-sentiment")
async def get_news_sentiment(
    symbol: str = Query("BTC/USDT"),
    limit: int = Query(20, ge=5, le=50),
    _user: dict = Depends(get_current_user),
):
    """获取新闻情绪分析"""
    try:
        engine = get_news_sentiment_engine()
        report = await engine.analyze(symbol, news_limit=limit, use_ai=True)
        return {"success": True, "data": report.to_dict()}
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


@router.get("/news-sentiment/keyword")
async def get_news_sentiment_keyword(
    symbol: str = Query("BTC/USDT"),
    limit: int = Query(20, ge=5, le=50),
    _user: dict = Depends(get_current_user),
):
    """获取新闻情绪分析（仅关键词规则）"""
    try:
        engine = get_news_sentiment_engine()
        report = await engine.analyze(symbol, news_limit=limit, use_ai=False)
        return {"success": True, "data": report.to_dict()}
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


# ------------------------------------------------------------------
# 技术指标 & 预测信号
# ------------------------------------------------------------------

def _ema(values: np.ndarray, period: int) -> np.ndarray:
    """指数移动平均"""
    alpha = 2.0 / (period + 1)
    out = np.empty_like(values, dtype=float)
    out[0] = values[0]
    for i in range(1, len(values)):
        out[i] = alpha * values[i] + (1 - alpha) * out[i - 1]
    return out


def _rsi(closes: np.ndarray, period: int = 14) -> float | None:
    """RSI(14)"""
    if len(closes) < period + 1:
        return None
    deltas = np.diff(closes)
    gains = np.where(deltas > 0, deltas, 0.0)
    losses = np.where(deltas < 0, -deltas, 0.0)
    avg_gain = gains[:period].mean()
    avg_loss = losses[:period].mean()
    for i in range(period, len(deltas)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return float(100.0 - 100.0 / (1.0 + rs))


def _compute_indicators(ohlcv_data: list[dict]) -> dict | None:
    """从 OHLCV 计算全套技术指标。返回 dict 或 None（数据不足）"""
    if not ohlcv_data or len(ohlcv_data) < 60:
        return None
    closes = np.array([c["close"] for c in ohlcv_data], dtype=float)
    highs = np.array([c["high"] for c in ohlcv_data], dtype=float)
    lows = np.array([c["low"] for c in ohlcv_data], dtype=float)
    volumes = np.array([c.get("volume", 0) for c in ohlcv_data], dtype=float)

    # RSI(14)
    rsi = _rsi(closes, 14)

    # MACD(12, 26, 9)
    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    macd_line = ema12 - ema26
    macd_signal = _ema(macd_line, 9)
    macd = float(macd_line[-1])
    macd_sig = float(macd_signal[-1])

    # 布林带(20, 2σ)
    bb_period = 20
    if len(closes) >= bb_period:
        sma20 = closes[-bb_period:].mean()
        std20 = closes[-bb_period:].std(ddof=0)
        bb_upper = float(sma20 + 2 * std20)
        bb_lower = float(sma20 - 2 * std20)
        bb_width = float(bb_upper - bb_lower)
    else:
        bb_upper = bb_lower = bb_width = 0.0

    # EMA 9 / 21 / 50
    ema_9 = float(_ema(closes, 9)[-1])
    ema_21 = float(_ema(closes, 21)[-1])
    ema_50 = float(_ema(closes, 50)[-1])

    # ATR(14)
    atr_period = 14
    if len(closes) > atr_period:
        tr = np.maximum(
            highs[1:] - lows[1:],
            np.maximum(
                np.abs(highs[1:] - closes[:-1]),
                np.abs(lows[1:] - closes[:-1]),
            ),
        )
        atr = float(tr[-atr_period:].mean())
    else:
        atr = 0.0

    # Volume Ratio（当前 / 过去 20 根均值）
    vol_period = 20
    if len(volumes) >= vol_period + 1 and volumes[-vol_period:-1].mean() > 0:
        volume_ratio = float(volumes[-1] / volumes[-vol_period:-1].mean())
    else:
        volume_ratio = 1.0

    return {
        "rsi": rsi,
        "macd": macd,
        "macd_signal": macd_sig,
        "bb_upper": bb_upper,
        "bb_lower": bb_lower,
        "bb_width": bb_width,
        "ema_9": ema_9,
        "ema_21": ema_21,
        "ema_50": ema_50,
        "atr": atr,
        "volume_ratio": volume_ratio,
        "current_price": float(closes[-1]),
    }


@router.get("/indicators")
def get_indicators(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("1h"),
    _user: dict = Depends(get_current_user),
):
    """获取技术指标（RSI / MACD / 布林带 / EMA / ATR / Volume Ratio）"""
    try:
        ohlcv, _ = get_ohlcv(symbol, timeframe, limit=200)
        result = _compute_indicators(ohlcv)
        if result is None:
            return {"success": False, "error": "insufficient data", "data": None}
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


@router.get("/predict")
def get_prediction(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("1h"),
    _user: dict = Depends(get_current_user),
):
    """基于技术指标给出预测信号（buy / sell / hold）+ 概率 + 置信度"""
    try:
        ohlcv, _ = get_ohlcv(symbol, timeframe, limit=200)
        ind = _compute_indicators(ohlcv)
        if ind is None:
            return {"success": False, "error": "insufficient data", "data": None}

        rsi = ind["rsi"] or 50.0
        macd = ind["macd"]
        macd_sig = ind["macd_signal"]
        macd_hist = macd - macd_sig
        price = ind["current_price"]
        ema_9 = ind["ema_9"]
        ema_21 = ind["ema_21"]

        # 评分：多信号加权
        score = 0.0
        # RSI 贡献（30 以下偏多，70 以上偏空）
        if rsi < 30:
            score += (30 - rsi) / 30 * 0.4
        elif rsi > 70:
            score -= (rsi - 70) / 30 * 0.4
        # MACD 柱贡献
        score += max(-0.3, min(0.3, macd_hist / max(abs(macd), 1e-9) * 0.3)) if macd != 0 else 0
        # EMA 排列贡献（金叉/死叉）
        if ema_9 > ema_21:
            score += 0.2
        else:
            score -= 0.2

        # 归一化到概率
        prob_up = float(max(0.05, min(0.95, 0.5 + score)))
        prob_down = 1.0 - prob_up

        if prob_up > 0.6:
            signal = "buy"
            prediction = "up"
        elif prob_up < 0.4:
            signal = "sell"
            prediction = "down"
        else:
            signal = "hold"
            prediction = "up" if prob_up >= 0.5 else "down"

        confidence = float(abs(prob_up - 0.5) * 2)

        return {
            "success": True,
            "data": {
                "signal": signal,
                "prediction": prediction,
                "current_price": price,
                "prob_up": prob_up,
                "prob_down": prob_down,
                "confidence": confidence,
                "rsi": rsi,
                "macd_hist": float(macd_hist),
            },
        }
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


@router.post("/train")
async def train_model_endpoint(
    symbol: str = Query("BTC/USDT"),
    timeframe: str = Query("1h"),
    limit: int = Query(1000),
    _user: dict = Depends(get_current_user),
):
    """训练 ML 模型（v2.0: 补上此前前端调用但后端缺失的 /train 路由）"""
    import asyncio
    from ml.models import train_model
    try:
        result = await asyncio.to_thread(train_model, symbol, timeframe, limit)
        return {"success": True, "data": result}
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}
