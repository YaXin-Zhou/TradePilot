"""策略管理 API — 薄层：参数校验 → 调用 service → 构造响应"""
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from typing import Optional

from db.models import StrategyType, StrategyStatus
from auth.deps import get_current_user
from services.strategy_service import (
    list_all_strategies,
    create_strategy,
    get_strategy_detail,
    update_strategy,
    start_strategy,
    stop_strategy,
    delete_strategy,
)
from services.strategy_pool import strategy_pool, StrategyStatus as PoolStatus
from services.online_learner import online_learner
from services.strategy_log import get_logs

router = APIRouter(prefix="/api/strategies", tags=["strategies"])


class StrategyCreate(BaseModel):
    name: str
    type: StrategyType
    symbol: str = "BTC/USDT"
    config: dict = {}


class StrategyUpdate(BaseModel):
    status: Optional[StrategyStatus] = None
    config: Optional[dict] = None


@router.get("/")
async def list_strategies():
    return {"success": True, "data": await list_all_strategies()}


@router.post("/")
async def api_create_strategy(req: StrategyCreate, _user: dict = Depends(get_current_user)):
    return await create_strategy(req.name, req.type, req.symbol, req.config)


@router.get("/{strategy_id}")
async def api_get_strategy(strategy_id: str):
    return await get_strategy_detail(strategy_id)


@router.patch("/{strategy_id}")
async def api_update_strategy(strategy_id: str, req: StrategyUpdate, _user: dict = Depends(get_current_user)):
    return await update_strategy(strategy_id, req.status, req.config)


@router.post("/{strategy_id}/start")
async def api_start_strategy(strategy_id: str, _user: dict = Depends(get_current_user)):
    return await start_strategy(strategy_id)


@router.post("/{strategy_id}/stop")
async def api_stop_strategy(strategy_id: str, _user: dict = Depends(get_current_user)):
    return await stop_strategy(strategy_id)


@router.delete("/{strategy_id}")
async def api_delete_strategy(strategy_id: str, _user: dict = Depends(get_current_user)):
    return await delete_strategy(strategy_id)


# ------------------------------------------------------------------
# 策略仓库管理：批量删除 + 自动清理
# ------------------------------------------------------------------

class BatchDeleteRequest(BaseModel):
    strategy_ids: list[str]
    confirm: bool = False  # 必须为 true 才执行

@router.post("/warehouse/cleanup")
async def api_auto_cleanup(_user: dict = Depends(get_current_user)):
    """自动清理垃圾策略：
    - 休眠超过30天且胜率<30%
    - 已被策略池淘汰（status=ELIMINATED）超过14天
    - 夏普<0 且创建超过7天且从未启动过
    """
    from services.strategy_service import auto_cleanup_strategies
    result = await auto_cleanup_strategies()
    return {"success": True, "data": result}

@router.post("/warehouse/batch-delete")
async def api_batch_delete(req: BatchDeleteRequest, _user: dict = Depends(get_current_user)):
    """批量删除策略"""
    if not req.confirm:
        return {"success": False, "error": "需 confirm=true 确认批量删除"}
    if not req.strategy_ids:
        return {"success": False, "error": "请提供要删除的策略ID列表"}
    from services.strategy_service import batch_delete_strategies
    result = await batch_delete_strategies(req.strategy_ids)
    return {"success": True, "data": result}


# ------------------------------------------------------------------
# 策略日志
# ------------------------------------------------------------------

@router.get("/{strategy_id}/logs")
async def api_get_strategy_logs(
    strategy_id: str,
    limit: int = Query(100, ge=10, le=500),
    event_type: Optional[str] = Query(None),
    _user: dict = Depends(get_current_user),
):
    """获取策略运行日志（最近 N 条，可按类型过滤）。
    内存缓冲区为空时自动从 DB 恢复。
    """
    logs = get_logs(strategy_id, limit=limit, event_type=event_type)
    if not logs:
        # 内存为空，尝试从 DB 恢复
        from services.strategy_log import recover_from_db
        await recover_from_db(strategy_id, limit=limit)
        logs = get_logs(strategy_id, limit=limit, event_type=event_type)
    return {"success": True, "data": logs}

# ------------------------------------------------------------------
# 策略池管理
# ------------------------------------------------------------------

@router.get("/pool/summary")
def get_pool_summary(_user: dict = Depends(get_current_user)):
    """策略池仪表盘摘要"""
    return {"success": True, "data": strategy_pool.summary()}


@router.get("/pool/correlation")
def get_pool_correlation(_user: dict = Depends(get_current_user)):
    """策略池相关性矩阵"""
    return {"success": True, "data": strategy_pool.correlation_matrix()}


class RegisterPoolRequest(BaseModel):
    name: str
    strategy_type: str
    weight: float = 0.0


@router.post("/pool/{strategy_id}/register")
def register_to_pool(strategy_id: str, req: RegisterPoolRequest,
                     _user: dict = Depends(get_current_user)):
    """注册策略到池"""
    s = strategy_pool.register(strategy_id, req.name, req.strategy_type, req.weight)
    return {"success": True, "data": s.to_dict()}


@router.post("/pool/{strategy_id}/status")
def set_pool_status(strategy_id: str, status: str,
                    _user: dict = Depends(get_current_user)):
    """设置策略池状态"""
    try:
        ps = PoolStatus(status)
    except ValueError:
        return {"success": False, "error": f"Invalid status: {status}"}
    strategy_pool.set_status(strategy_id, ps)
    return {"success": True, "data": strategy_pool.get(strategy_id).to_dict() if strategy_pool.get(strategy_id) else None}


@router.delete("/pool/{strategy_id}")
def remove_from_pool(strategy_id: str, _user: dict = Depends(get_current_user)):
    """从策略池移除"""
    strategy_pool.remove(strategy_id)
    return {"success": True}


# ------------------------------------------------------------------
# 在线学习权重
# ------------------------------------------------------------------

class LearnerUpdateRequest(BaseModel):
    returns: dict[str, float]
    sleeping: list[str] = []
    regime: str = ""


@router.post("/learner/update")
def update_learner(req: LearnerUpdateRequest, _user: dict = Depends(get_current_user)):
    """更新在线学习权重"""
    result = online_learner.update(req.returns, req.sleeping, req.regime)
    return {"success": True, "data": result.to_dict()}


@router.get("/learner/weights")
def get_learner_weights(_user: dict = Depends(get_current_user)):
    """获取当前学习权重"""
    return {"success": True, "data": online_learner.get_weights()}


@router.get("/learner/state")
def get_learner_state(_user: dict = Depends(get_current_user)):
    """获取完整学习器状态"""
    return {"success": True, "data": online_learner.get_all_states()}


@router.post("/learner/reset")
def reset_learner(_user: dict = Depends(get_current_user)):
    """重置学习器"""
    online_learner.reset()
    return {"success": True}


# ------------------------------------------------------------------
# AI 心跳 (Heartbeat)
# ------------------------------------------------------------------

class HeartbeatTriggerRequest(BaseModel):
    pass


@router.post("/heartbeat/run")
async def run_heartbeat(_user: dict = Depends(get_current_user)):
    """手动触发一次 AI 心跳审查"""
    try:
        from tasks.ai_heartbeat import get_heartbeat
        hb = get_heartbeat()
        result = await hb.beat()
        return {"success": True, "data": result.to_dict()}
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}


@router.get("/heartbeat/history")
def get_heartbeat_history(
    limit: int = 10,
    _user: dict = Depends(get_current_user),
):
    """获取心跳历史"""
    try:
        from tasks.ai_heartbeat import get_heartbeat
        hb = get_heartbeat()
        history = hb.get_history(limit)
        return {"success": True, "data": history}
    except Exception as e:
        return {"success": False, "error": str(e), "data": []}


@router.get("/heartbeat/last")
def get_heartbeat_last(_user: dict = Depends(get_current_user)):
    """获取最近一次心跳结果"""
    try:
        from tasks.ai_heartbeat import get_heartbeat
        hb = get_heartbeat()
        last = hb.get_last_cycle()
        return {"success": True, "data": last}
    except Exception as e:
        return {"success": False, "error": str(e), "data": None}
