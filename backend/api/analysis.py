"""分析 API — 市场状态 / 风控策略"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from auth.deps import get_current_user
from services.market_service import get_ohlcv
from services.regime_detector import regime_detector
from services.risk_engine import risk_engine, RiskPolicy

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
