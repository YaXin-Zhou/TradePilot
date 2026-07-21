"""策略管理服务层 — CRUD + 启停 + AI 策略自动入库"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Strategy, StrategyType, StrategyStatus
from db.database import async_session
from core.logger import log

# AI 策略类型字符串 → StrategyType 枚举映射
_AI_TYPE_MAP: dict[str, StrategyType] = {
    "ma_crossover": StrategyType.MA_CROSS,
    "ma_cross": StrategyType.MA_CROSS,
    "rsi": StrategyType.RSI,
    "bollinger": StrategyType.BOLLINGER,
    "grid": StrategyType.GRID,
    "custom": StrategyType.CUSTOM,
}


async def list_all_strategies() -> list[dict]:
    """获取所有策略列表"""
    async with async_session() as session:
        result = await session.execute(select(Strategy))
        strategies = result.scalars().all()
        return [
            {
                "id": s.id,
                "name": s.name,
                "type": s.type.value,
                "status": s.status.value,
                "symbol": s.symbol,
                "config": s.config,
                "total_pnl": s.total_pnl,
                "total_trades": s.total_trades,
                "win_rate": s.win_rate,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            }
            for s in strategies
        ]


async def create_strategy(name: str, stype: StrategyType, symbol: str = "BTC/USDT", config: dict | None = None) -> dict:
    """创建新策略"""
    async with async_session() as session:
        strategy = Strategy(
            name=name,
            type=stype,
            symbol=symbol,
            config=config or {},
        )
        session.add(strategy)
        await session.commit()
        await session.refresh(strategy)
        return {"success": True, "data": {"id": strategy.id}}


async def get_strategy_detail(strategy_id: str) -> dict:
    """获取单个策略详情"""
    async with async_session() as session:
        result = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
        s = result.scalar_one_or_none()
        if not s:
            return {"success": False, "error": "not found"}
        return {
            "success": True,
            "data": {
                "id": s.id,
                "name": s.name,
                "type": s.type.value,
                "status": s.status.value,
                "symbol": s.symbol,
                "config": s.config,
                "total_pnl": s.total_pnl,
                "total_trades": s.total_trades,
                "win_rate": s.win_rate,
                "sharpe_ratio": s.sharpe_ratio,
                "max_drawdown": s.max_drawdown,
                "created_at": s.created_at.isoformat() if s.created_at else None,
            },
        }


async def update_strategy(strategy_id: str, status: StrategyStatus | None = None, config: dict | None = None) -> dict:
    """更新策略状态或配置"""
    async with async_session() as session:
        result = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
        s = result.scalar_one_or_none()
        if not s:
            return {"success": False, "error": "not found"}
        if status:
            s.status = status
        if config:
            s.config = config
        await session.commit()
        return {"success": True}


async def start_strategy(strategy_id: str) -> dict:
    """启动策略。

    P1-4: 统一使用 _build_strategy_obj 构建策略对象，支持全部策略类型
    （GRID/MA_CROSS/SMA_CROSS/RSI/BOLLINGER/CUSTOM/ML_SIGNAL/AI_GENERATED）。
    """
    async with async_session() as session:
        r = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
        s = r.scalar_one_or_none()
        if not s:
            return {"success": False, "error": "not found"}

        from strategies.runner import _build_strategy_obj
        instance = _build_strategy_obj(s)
        if instance is None:
            return {"success": False, "error": f"unsupported strategy type: {s.type.value}"}

        await runner.start(strategy_id, instance)
        s.status = StrategyStatus.RUNNING
        s.started_at = datetime.now(timezone.utc)
        await session.commit()
    return {"success": True}


async def stop_strategy(strategy_id: str) -> dict:
    """停止策略"""
    await runner.stop(strategy_id)
    return {"success": True}


async def delete_strategy(strategy_id: str) -> dict:
    """删除策略"""
    async with async_session() as session:
        result = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
        s = result.scalar_one_or_none()
        if not s:
            return {"success": False, "error": "not found"}
        await session.delete(s)
        await session.commit()
        return {"success": True}


async def save_ai_strategy(
    name: str,
    strategy_type: str,
    symbol: str = "BTC/USDT",
    config: dict | None = None,
    backtest: dict | None = None,
    description: str = "",
    user_id: str = "",
) -> dict:
    """AI 生成策略自动入库 — 创建策略记录 + 写入回测指标

    Args:
        name: 策略名称（AI 自动生成或用户指定）
        strategy_type: AI 返回的策略类型字符串（如 "ma_crossover"）
        symbol: 交易对
        config: 策略参数（如 {fast: 10, slow: 30}）
        backtest: 回测结果（sharpe_ratio, win_rate, total_trades, max_drawdown_pct, total_return_pct）
        description: AI 策略描述

    Returns:
        {"success": True, "data": {"id": "xxx"}} 或 {"success": False, "error": "..."}
    """
    try:
        # 类型映射
        stype = _AI_TYPE_MAP.get(strategy_type, StrategyType.AI_GENERATED)

        async with async_session() as session:
            strategy = Strategy(
                name=name,
                type=stype,
                symbol=symbol,
                config={
                    **(config or {}),
                    "strategy_type": strategy_type,  # 保留 AI 原始类型名
                    "description": description,
                },
                status=StrategyStatus.DRAFT,
                user_id=user_id or "default",
            )

            # 写入回测指标
            if backtest:
                strategy.total_trades = int(backtest.get("total_trades", 0))
                strategy.win_rate = float(backtest.get("win_rate", 0))
                strategy.sharpe_ratio = float(backtest.get("sharpe_ratio", 0))
                strategy.max_drawdown = float(backtest.get("max_drawdown_pct", 0))
                strategy.total_pnl = float(backtest.get("total_return_pct", 0))

            session.add(strategy)
            await session.commit()
            await session.refresh(strategy)
            sid = strategy.id

        log.info(f"AI 策略自动入库: {sid} ({name}, {strategy_type})")
        return {"success": True, "data": {"id": sid}}

    except Exception as e:
        log.error(f"AI 策略入库失败: {e}")
        return {"success": False, "error": str(e)[:200]}
