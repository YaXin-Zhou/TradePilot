"""策略管理服务层 — CRUD + 启停"""
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Strategy, StrategyType, StrategyStatus
from db.database import async_session
from strategies.runner import runner
from strategies.custom import CustomStrategy


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
    """启动策略"""
    async with async_session() as session:
        r = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
        s = r.scalar_one_or_none()
        if not s:
            return {"success": False, "error": "not found"}

        if s.type == StrategyType.CUSTOM:
            instance = CustomStrategy(s.id, s.name, s.config)
        elif s.type == StrategyType.GRID:
            from strategies.grid import GridStrategy
            instance = GridStrategy(s.id, s.name, s.config)
        else:
            return {"success": False, "error": "unsupported type"}

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
