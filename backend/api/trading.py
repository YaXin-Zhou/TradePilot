"""交易 API — Phase 8 实盘就绪版

新增端点：
  POST /api/trading/emergency-stop    触发紧急停止（撤单+平仓+停策略）
  POST /api/trading/emergency-reset   解除紧急停止（需二次确认）
  GET  /api/trading/kill-switch       查询紧急停止状态
  POST /api/trading/cancel-all        撤销所有挂单

改动：
  - cancel-order 真正撤单（原为空操作）
  - limit-order / market-order 加 confirm_live 参数（实盘二次确认）
"""
from fastapi import APIRouter, Depends
from auth.deps import get_current_user, require_admin
from config import settings
from pydantic import BaseModel
from services.trading_service import (
    get_balance, place_limit_order, place_market_order,
    cancel_order, cancel_all_orders, get_open_orders, get_trade_history,
    execute_emergency_stop,
)
from core.kill_switch import kill_switch
from core.logger import log

router = APIRouter(prefix="/api/trading", tags=["trading"])


class LimitOrderRequest(BaseModel):
    symbol: str = settings.DEFAULT_SYMBOL
    side: str
    amount: float
    price: float
    confirm_live: bool = False  # 实盘模式二次确认
    account_id: str = "default"  # M3: 多账户支持


class CancelOrderRequest(BaseModel):
    symbol: str = settings.DEFAULT_SYMBOL
    order_id: str


class MarketOrderRequest(BaseModel):
    symbol: str = settings.DEFAULT_SYMBOL
    side: str
    amount: float
    confirm_live: bool = False  # 实盘模式二次确认
    account_id: str = "default"  # M3: 多账户支持


class EmergencyStopRequest(BaseModel):
    reason: str = ""
    confirm: bool = False  # 必须为 true 才执行


class EmergencyResetRequest(BaseModel):
    confirm: bool = False  # 必须为 true 才执行


@router.get("/balance")
async def api_get_balance(_user: dict = Depends(get_current_user)):
    data, is_mock = await get_balance()
    resp = {"success": True, "data": data}
    if is_mock:
        resp["_mock"] = True
    return resp


@router.post("/limit-order")
async def api_limit_order(req: LimitOrderRequest, _user: dict = Depends(require_admin)):
    # v6: 手动交易已取消，仅策略自动交易
    return {"success": False, "error": "手动交易已禁用，请通过策略(自动交易)下单"}


@router.post("/cancel-order")
async def api_cancel_order(req: CancelOrderRequest, _user: dict = Depends(require_admin)):
    """Phase 8: 真正调用交易所撤单（原为空操作）"""
    ok, msg = await cancel_order(req.order_id, req.symbol)
    if not ok:
        return {"success": False, "error": msg}
    return {"success": True, "data": {"cancelled": True, "order_id": req.order_id}}


@router.post("/cancel-all")
async def api_cancel_all(symbol: str = "", _user: dict = Depends(require_admin)):
    """撤销所有挂单（可指定交易对）"""
    n, msg = await cancel_all_orders(symbol)
    return {"success": True, "data": {"cancelled_count": n, "message": msg}}


@router.post("/market-order")
async def api_market_order(req: MarketOrderRequest, _user: dict = Depends(require_admin)):
    # v6: 手动交易已取消，仅策略自动交易
    return {"success": False, "error": "手动交易已禁用，请通过策略(自动交易)下单"}


@router.get("/open-orders")
async def api_open_orders(symbol: str = settings.DEFAULT_SYMBOL, _user: dict = Depends(get_current_user)):
    data, is_mock = get_open_orders(symbol)
    resp = {"success": True, "data": data}
    if is_mock:
        resp["_mock"] = True
    return resp


@router.get("/trades")
async def api_trades(symbol: str = settings.DEFAULT_SYMBOL, limit: int = 50, _user: dict = Depends(get_current_user)):
    data, is_mock = get_trade_history(symbol, limit)
    resp = {"success": True, "data": data}
    if is_mock:
        resp["_mock"] = True
    return resp


# ------------------------------------------------------------------
# 紧急停止（Kill Switch）
# ------------------------------------------------------------------

@router.get("/kill-switch")
async def api_kill_switch_status(_user: dict = Depends(get_current_user)):
    """查询紧急停止状态"""
    return {"success": True, "data": kill_switch.get_state()}


@router.post("/emergency-stop")
async def api_emergency_stop(req: EmergencyStopRequest, _user: dict = Depends(require_admin)):
    """触发紧急停止：撤所有挂单 + 市价平所有持仓 + 停所有策略

    需 confirm=true 才执行。触发后所有交易被冻结，需 POST /emergency-reset 解除。
    """
    if not req.confirm:
        return {"success": False, "error": "需 confirm=true 才能执行紧急停止"}
    if kill_switch.is_triggered:
        return {"success": False, "error": "紧急停止已触发，无需重复操作", "data": kill_switch.get_state()}

    by = f"user:{_user.get('id', 'unknown')}"
    results = await execute_emergency_stop(by=by, reason=req.reason or "Manual trigger via API")
    return {
        "success": True,
        "data": {
            "kill_switch": kill_switch.get_state(),
            "actions": results,
        },
    }


@router.post("/emergency-reset")
async def api_emergency_reset(req: EmergencyResetRequest, _user: dict = Depends(require_admin)):
    """解除紧急停止。需 confirm=true 才执行。"""
    if not req.confirm:
        return {"success": False, "error": "需 confirm=true 才能解除紧急停止"}
    if kill_switch.is_armed:
        return {"success": False, "error": "紧急停止未触发，无需解除"}
    state = kill_switch.reset()
    return {"success": True, "data": state}


# ------------------------------------------------------------------
# 手动交易风控设置
# ------------------------------------------------------------------

class ManualRiskSettings(BaseModel):
    max_order_usdt: float | None = None
    max_daily_loss_usdt: float | None = None
    min_order_usdt: float | None = None
    max_position_usdt: float | None = None
    enabled: bool | None = None


@router.get("/manual-risk-settings")
def get_manual_risk_settings(_user: dict = Depends(get_current_user)):
    """获取手动交易风控设置"""
    from core.app_config import get_manual_risk
    return {"success": True, "data": get_manual_risk()}


@router.put("/manual-risk-settings")
async def update_manual_risk_settings(req: ManualRiskSettings, _user: dict = Depends(require_admin)):
    """更新手动交易风控设置"""
    import json
    from sqlalchemy import text
    from db.database import async_session
    from core.app_config import MANUAL_RISK_DEFAULTS

    # 读取当前值
    current = MANUAL_RISK_DEFAULTS.copy()
    try:
        async with async_session() as session:
            result = await session.execute(
                text("SELECT value FROM app_config WHERE key = 'manual_risk_settings'")
            )
            row = result.fetchone()
            if row:
                val = row[0]
                current = json.loads(val) if isinstance(val, str) else val
    except Exception as e:
        log.warning(f"读取手动风控设置失败，使用默认值: {e}")

    # 合并新值
    current.update({k: v for k, v in req.dict().items() if v is not None})
    value_json = json.dumps(current, ensure_ascii=False)

    # 写入 DB
    async with async_session() as session:
        await session.execute(
            text("""
                INSERT INTO app_config (key, value)
                VALUES ('manual_risk_settings', :value)
                ON CONFLICT (key) DO UPDATE SET value = :value
            """),
            {"value": value_json},
        )
        await session.commit()

    # 刷新缓存
    from core.app_config import refresh_cache
    refresh_cache("manual_risk_settings")

    return {"success": True, "data": current}
