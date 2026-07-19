"""投资组合服务层 — 余额查询、交易历史、绩效分析

P1-1: 移除所有 Mock 回退 — 故障时返回明确错误，不返回假数据。
"""
from datetime import datetime, timezone

from sqlalchemy import select, func
from core.exchange import ExchangeClient
from config import settings
from db.models import Trade, Strategy
from db.database import async_session
from core.logger import log

_exchange = ExchangeClient(
    exchange_name=settings.EXCHANGE_NAME,
    api_key=settings.EXCHANGE_API_KEY,
    secret=settings.EXCHANGE_SECRET,
    passphrase=settings.EXCHANGE_PASSPHRASE,
    testnet=settings.EXCHANGE_TESTNET,
)


async def get_portfolio_summary() -> dict:
    """获取投资组合摘要（余额 + 统计）。

    P1-1: 交易所查询失败时返回 success=False + 错误信息，不再返回假数据。
    DB 查询失败时返回零值（不阻塞前端展示余额）。
    """
    try:
        balance = _exchange.fetch_balance()
        ticker = _exchange.fetch_ticker(settings.DEFAULT_SYMBOL)
        total_usdt = balance.get("USDT", {}).get("total", 0)
        btc_balance = balance.get("BTC", {}).get("total", 0)
        estimated_total = total_usdt + btc_balance * ticker["last"]
    except Exception as e:
        log.warning(f"Portfolio: exchange fetch failed: {e}")
        return {
            "success": False,
            "error": f"交易所连接失败: {e}",
            "data": None,
        }

    # DB 统计（失败不阻塞，返回零值）
    total_trades = 0
    total_pnl = 0.0
    active_strategies = 0
    try:
        async with async_session() as session:
            total_trades = await session.scalar(select(func.count(Trade.id))) or 0
            total_pnl = await session.scalar(select(func.coalesce(func.sum(Trade.profit), 0))) or 0.0
            active_strategies = await session.scalar(
                select(func.count(Strategy.id)).where(Strategy.status == "running")
            ) or 0
    except Exception as e:
        log.warning(f"Portfolio: DB stats failed (returning zeros): {e}")

    return {
        "success": True,
        "data": {
            "total_value_usdt": round(estimated_total, 2),
            "usdt_balance": round(total_usdt, 2),
            "btc_balance": round(btc_balance, 6),
            "btc_price": round(ticker["last"], 2),
            "total_trades": total_trades,
            "total_pnl": round(float(total_pnl), 4),
            "active_strategies": active_strategies,
        },
    }


async def get_trade_history(limit: int = 100) -> dict:
    """获取交易历史（DB 查询，无记录返回空列表）。

    P1-1: 移除 Mock 回退 — DB 无交易记录时返回空列表，不生成假数据。
    """
    try:
        async with async_session() as session:
            result = await session.execute(
                select(Trade).order_by(Trade.closed_at.desc()).limit(limit)
            )
            trades = result.scalars().all()
            return {
                "success": True,
                "data": [
                    {
                        "id": t.id, "symbol": t.symbol,
                        "buy_price": t.buy_price, "sell_price": t.sell_price,
                        "quantity": t.quantity, "profit": t.profit,
                        "profit_pct": t.profit_pct,
                        "opened_at": t.opened_at.isoformat() if t.opened_at else None,
                        "closed_at": t.closed_at.isoformat() if t.closed_at else None,
                    }
                    for t in trades
                ],
            }
    except Exception as e:
        log.error(f"Trade history query failed: {e}")
        return {"success": False, "error": str(e), "data": []}


async def get_performance() -> dict:
    """获取绩效分析（PnL 计算 + 曲线）。

    P1-1: 移除 Mock 回退 — DB 无交易记录时返回零值统计，不生成假数据。
    """
    try:
        async with async_session() as session:
            result = await session.execute(select(Trade).order_by(Trade.closed_at.asc()))
            trades = result.scalars().all()
            if not trades:
                return {
                    "success": True,
                    "data": {
                        "total_pnl": 0.0,
                        "total_trades": 0,
                        "win_rate": 0.0,
                        "wins": 0,
                        "losses": 0,
                        "pnl_curve": [],
                    },
                }

            total_pnl = sum(t.profit for t in trades)
            wins = sum(1 for t in trades if t.profit > 0)
            win_rate = wins / len(trades) * 100 if trades else 0
            cumulative = 0.0
            pnl_curve = []
            for t in trades:
                cumulative += t.profit
                pnl_curve.append({
                    "date": t.closed_at.isoformat() if t.closed_at else None,
                    "pnl": cumulative,
                })
            return {
                "success": True,
                "data": {
                    "total_pnl": round(total_pnl, 4),
                    "total_trades": len(trades),
                    "win_rate": round(win_rate, 2),
                    "wins": wins,
                    "losses": len(trades) - wins,
                    "pnl_curve": pnl_curve,
                },
            }
    except Exception as e:
        log.error(f"Performance query failed: {e}")
        return {"success": False, "error": str(e), "data": None}
