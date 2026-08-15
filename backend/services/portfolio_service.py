"""投资组合服务层 — 余额查询、交易历史、绩效分析、浮动盈亏

P1-1: 移除所有 Mock 回退 — 故障时返回明确错误，不返回假数据。
v1.2: 新增浮动盈亏计算 — 从交易所成交记录获取平均买入成本，结合实时价格计算未实现盈亏。
v1.3: 统一使用 shared_exchange 避免多 worker 下实例状态不一致。
"""
from datetime import datetime, timezone

from sqlalchemy import select, func
import core.exchange as exmod
from config import settings
from db.models import Trade, Strategy, Order, OrderSide, OrderStatus
from db.database import async_session
from core.logger import log


def _get_exchange():
    """动态获取 shared_exchange 实例（避免热重建后引用过期）"""
    return exmod.shared_exchange


async def get_portfolio_summary() -> dict:
    """获取投资组合摘要（余额 + 统计）。

    P1-1: 交易所查询失败时返回 success=False + 错误信息，不再返回假数据。
    DB 查询失败时返回零值（不阻塞前端展示余额）。
    """
    try:
        _exchange = _get_exchange()
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


async def _get_avg_buy_cost(symbols: list[str]) -> dict[str, dict]:
    """获取每个币种的平均买入成本。

    优先从交易所 fetch_my_trades() 获取真实成交记录（准确），
    回退到 DB orders 表（status=CLOSED）。

    返回 {symbol: {avg_price, total_cost, total_qty, sell_cost, sell_qty, realized_pnl}}
    """
    result_map: dict[str, dict] = {}

    _exchange = _get_exchange()
    # 1. 优先从交易所获取成交记录
    for symbol in symbols:
        result_map[symbol] = {
            "buy_cost": 0.0,
            "buy_qty": 0.0,
            "sell_cost": 0.0,
            "sell_qty": 0.0,
            "avg_price": None,
            "realized_pnl": 0.0,
        }
        try:
            trades = _exchange.fetch_my_trades(symbol, limit=50)
            for tr in trades:
                side = tr.get("side", "")
                price = float(tr.get("price", 0) or 0)
                amount = float(tr.get("amount", 0) or 0)
                cost = float(tr.get("cost", 0) or price * amount or 0)
                entry = result_map[symbol]
                if side == "buy":
                    entry["buy_cost"] += cost
                    entry["buy_qty"] += amount
                elif side == "sell":
                    entry["sell_cost"] += cost
                    entry["sell_qty"] += amount
        except Exception as e:
            log.debug(f"Positions: fetch_my_trades({symbol}) failed: {e}")

    # 2. 如果交易所无数据，回退到 DB orders 表
    db_needed = [s for s, v in result_map.items() if v["buy_qty"] == 0]
    if db_needed:
        try:
            async with async_session() as session:
                stmt = select(Order).where(
                    Order.symbol.in_(db_needed),
                    Order.status == OrderStatus.CLOSED,
                    Order.filled > 0,
                )
                rows = (await session.execute(stmt)).scalars().all()
                for o in rows:
                    entry = result_map.get(o.symbol)
                    if not entry:
                        continue
                    if o.side == OrderSide.BUY:
                        entry["buy_cost"] += float(o.cost or o.price * o.filled or 0)
                        entry["buy_qty"] += float(o.filled or 0)
                    elif o.side == OrderSide.SELL:
                        entry["sell_cost"] += float(o.cost or o.price * o.filled or 0)
                        entry["sell_qty"] += float(o.filled or 0)
        except Exception as e:
            log.warning(f"Positions: DB fallback avg cost query failed: {e}")

    # 3. 计算平均买入价 + 已实现盈亏
    for symbol, e in result_map.items():
        if e["buy_qty"] > 0:
            e["avg_price"] = e["buy_cost"] / e["buy_qty"]
            if e["sell_qty"] > 0:
                e["realized_pnl"] = e["sell_cost"] - e["sell_qty"] * e["avg_price"]

    return result_map


async def get_positions() -> dict:
    """获取当前合约持仓列表（v2.0 合约模式：fetch_positions 为真源）。

    返回多头/空头双向持仓，含开仓均价、标记价、未实现盈亏、名义价值、杠杆。
    合约持仓与现货余额解耦——不再用"非 USDT 余额"冒充持仓。
    """
    try:
        _exchange = _get_exchange()
        positions = _exchange.fetch_positions()
    except Exception as e:
        log.warning(f"Positions: exchange fetch failed: {e}")
        return {"success": False, "error": f"交易所连接失败: {e}", "data": []}

    result_positions = []
    total_notional = 0.0
    total_unrealized_pnl = 0.0

    for p in positions:
        contracts = float(p.get("contracts", 0) or 0)
        if contracts <= 0:
            continue
        symbol = p.get("symbol") or ""
        side = p.get("side", "")
        entry_price = float(p.get("entry_price", 0) or 0)
        mark_price = float(p.get("mark_price", 0) or 0)
        unrealized_pnl = float(p.get("unrealized_pnl", 0) or 0)
        notional = abs(float(p.get("notional", 0) or 0))
        leverage = float(p.get("leverage", 0) or 0)

        total_notional += notional
        total_unrealized_pnl += unrealized_pnl
        cost = notional - unrealized_pnl
        pnl_pct = (unrealized_pnl / cost * 100) if cost > 0 else 0.0

        result_positions.append({
            "symbol": symbol,
            "side": side,
            "contracts": round(contracts, 6),
            "entry_price": round(entry_price, 6),
            "mark_price": round(mark_price, 6),
            "notional_usdt": round(notional, 2),
            "unrealized_pnl": round(unrealized_pnl, 2),
            "pnl_pct": round(pnl_pct, 2),
            "leverage": leverage,
        })

    result_positions.sort(key=lambda p: p["notional_usdt"], reverse=True)

    log.info(f"Positions: found {len(result_positions)} contract positions, "
             f"total_notional={total_notional:.2f} USDT, "
             f"unrealized_pnl={total_unrealized_pnl:.2f} USDT")

    return {
        "success": True,
        "data": {
            "positions": result_positions,
            "total_notional_usdt": round(total_notional, 2),
            "total_unrealized_pnl": round(total_unrealized_pnl, 2),
            "count": len(result_positions),
        },
    }


async def get_realtime_assets() -> dict:
    """获取实时资金概览（v2.0 合约模式：账户权益 + 合约持仓未实现盈亏）。

    用于前端实时资金变化展示，聚合 USDT 权益 + 合约持仓盈亏。
    """
    try:
        _exchange = _get_exchange()
        balance = _exchange.fetch_balance()
        positions = _exchange.fetch_positions()
    except Exception as e:
        log.warning(f"RealtimeAssets: exchange fetch failed: {e}")
        return {"success": False, "error": f"交易所连接失败: {e}", "data": None}

    usdt_info = balance.get("USDT", {})
    usdt_free = float(usdt_info.get("free", 0) or 0)
    usdt_used = float(usdt_info.get("used", 0) or 0)
    usdt_total = float(usdt_info.get("total", 0) or 0)

    total_unrealized_pnl = 0.0
    positions_notional = 0.0
    for p in positions:
        total_unrealized_pnl += float(p.get("unrealized_pnl", 0) or 0)
        positions_notional += abs(float(p.get("notional", 0) or 0))

    # 合约账户权益 = USDT 总余额（已含未实现盈亏）；持仓名义价值仅作展示
    total_assets = usdt_total
    cost_basis = total_assets - total_unrealized_pnl
    total_pnl_pct = (total_unrealized_pnl / cost_basis * 100) if cost_basis > 0 else 0.0

    data = {
        "total_assets_usdt": round(total_assets, 2),
        "usdt_free": round(usdt_free, 2),
        "usdt_used": round(usdt_used, 2),
        "positions_value_usdt": round(positions_notional, 2),
        "total_unrealized_pnl": round(total_unrealized_pnl, 2),
        "total_pnl_pct": round(total_pnl_pct, 2),
        # v2.0: 合约模式下 24h 加权变化不再从现货余额推导，置 0（后续接入持仓标记价变化）
        "weighted_24h_change_pct": 0,
        "change_24h_usdt": 0,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }

    log.info(f"RealtimeAssets: equity={total_assets:.2f} USDT, "
             f"notional={positions_notional:.2f} USDT, "
             f"unrealized_pnl={total_unrealized_pnl:.2f} ({total_pnl_pct:.2f}%)")

    return {"success": True, "data": data}


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
