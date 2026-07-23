"""策略管理服务层 — CRUD + 启停 + AI 策略自动入库"""
from datetime import datetime, timezone, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from db.models import Strategy, StrategyType, StrategyStatus
from db.database import async_session
from core.logger import log
from services.strategy_log import append as log_event
from strategies.runner import runner

def _utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)

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
    """获取所有策略列表（运行中的置顶，其余按创建时间倒序）"""
    from sqlalchemy import case
    async with async_session() as session:
        result = await session.execute(
            select(Strategy).order_by(
                case((Strategy.status == StrategyStatus.RUNNING, 0), else_=1),
                Strategy.created_at.desc()
            )
        )
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
        log_event(strategy.id, "created", f"Strategy '{name}' created ({stype.value} on {symbol})")
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
        s.started_at = _utcnow_naive()
        await session.commit()
        log_event(strategy_id, "started", f"Strategy started ({s.type.value} {s.symbol})")
    return {"success": True}


async def stop_strategy(strategy_id: str) -> dict:
    """停止策略"""
    await runner.stop(strategy_id)
    log_event(strategy_id, "stopped", "Strategy stopped by user")
    return {"success": True}


async def delete_strategy(strategy_id: str) -> dict:
    """删除策略（级联清理关联记录）"""
    from sqlalchemy import text
    import traceback

    async with async_session() as session:
        result = await session.execute(select(Strategy).where(Strategy.id == strategy_id))
        s = result.scalar_one_or_none()
        if not s:
            return {"success": False, "error": "策略不存在"}
        name = s.name

        # 用 raw SQL 级联清理（一个事务内，从子表到父表顺序）
        try:
            # 按外键依赖顺序删除：event_logs → pool → runner_states → backtests → trades → positions → orders
            deletes = [
                ("DELETE FROM strategy_event_logs WHERE strategy_id = :sid", True),
                ("DELETE FROM strategy_pool_records WHERE id = :sid", True),
                ("DELETE FROM runner_states WHERE strategy_id = :sid", True),
                ("DELETE FROM backtest_results WHERE strategy_id = :sid", True),
                ("DELETE FROM trades WHERE strategy_id = :sid", True),
                ("DELETE FROM positions WHERE strategy_id = :sid", True),
                ("DELETE FROM orders WHERE strategy_id = :sid", True),
            ]
            for sql, _ in deletes:
                await session.execute(text(sql), {"sid": strategy_id})

            # 最后删策略本身
            await session.execute(
                text("DELETE FROM strategies WHERE id = :sid"), {"sid": strategy_id}
            )
            await session.commit()
            log_event(strategy_id, "deleted", f"Strategy '{name}' deleted (with cascade)")
            return {"success": True}
        except Exception as e:
            await session.rollback()
            log.error(f"Delete strategy {strategy_id} failed: {e}\n{traceback.format_exc()}")
            return {"success": False, "error": f"删除失败: {str(e)[:100]}"}


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


# ------------------------------------------------------------------
# 策略仓库管理：批量删除 + 自动清理
# ------------------------------------------------------------------

async def auto_cleanup_strategies() -> dict:
    """自动清理垃圾策略，返回清理统计"""
    from datetime import timedelta
    from sqlalchemy import delete, or_, and_

    now = _utcnow_naive()
    cleaned = 0
    details: list[str] = []

    async with async_session() as session:
        # 条件1：休眠超过30天 且 胜率<30%
        threshold_30d = now - timedelta(days=30)
        result = await session.execute(
            select(Strategy).where(
                Strategy.status == StrategyStatus.STOPPED,
                Strategy.updated_at < threshold_30d,
                Strategy.win_rate < 0.3,
                Strategy.total_trades > 0,  # 至少有交易记录才清理
            )
        )
        stale = result.scalars().all()
        for s in stale:
            details.append(f"STALE:{s.id[:8]} ({s.name}) stopped>30d, wr={s.win_rate:.0%}")
            await session.delete(s)
            cleaned += 1

        # 条件2：夏普<0 且 创建超过7天 且 从未启动过
        threshold_7d = now - timedelta(days=7)
        result = await session.execute(
            select(Strategy).where(
                Strategy.status == StrategyStatus.DRAFT,
                Strategy.created_at < threshold_7d,
                Strategy.sharpe_ratio < 0,
                Strategy.started_at.is_(None),
            )
        )
        poor = result.scalars().all()
        for s in poor:
            details.append(f"POOR:{s.id[:8]} ({s.name}) draft>7d, sharpe={s.sharpe_ratio:.2f}")
            await session.delete(s)
            cleaned += 1

        # 条件3：被淘汰（stopped且sharpe<-1.0）超过14天
        threshold_14d = now - timedelta(days=14)
        result = await session.execute(
            select(Strategy).where(
                Strategy.status == StrategyStatus.STOPPED,
                Strategy.updated_at < threshold_14d,
                Strategy.sharpe_ratio < -1.0,
            )
        )
        eliminated = result.scalars().all()
        for s in eliminated:
            details.append(f"ELIM:{s.id[:8]} ({s.name}) sharpe={s.sharpe_ratio:.2f} stopped>14d")
            await session.delete(s)
            cleaned += 1

        await session.commit()

    if cleaned > 0:
        log.info(f"Auto-cleanup: removed {cleaned} garbage strategies")
        for d in details[:10]:
            log.info(f"  {d}")

    return {"cleaned": cleaned, "details": details[:20]}


async def batch_delete_strategies(strategy_ids: list[str]) -> dict:
    """批量删除策略，先停止再删除"""
    deleted = 0
    errors: list[str] = []

    for sid in strategy_ids:
        try:
            # 先停止（避免 runner 还在运行）
            await stop_strategy(sid)
            result = await delete_strategy(sid)
            if result.get("success"):
                deleted += 1
            else:
                errors.append(f"{sid}: {result.get('error', 'unknown')}")
        except Exception as e:
            errors.append(f"{sid}: {e}")

    return {"deleted": deleted, "errors": errors, "total": len(strategy_ids)}


def _utcnow_naive():
    """统一返回 naive UTC datetime"""
    return datetime.now(timezone.utc).replace(tzinfo=None)
