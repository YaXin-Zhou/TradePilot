"""风险控制中间件 - 统一检查器"""
from datetime import datetime, timezone, timedelta
from config import settings
from db.database import async_session
from db.models import Order, OrderStatus, Trade
from sqlalchemy import select, func


class RiskManager:
    def __init__(self):
        self.max_position = settings.MAX_POSITION_SIZE_USDT
        self.max_daily_loss_pct = settings.MAX_DAILY_LOSS_PCT
        self.max_open_orders = settings.MAX_OPEN_ORDERS
        self.stop_loss_pct = settings.STOP_LOSS_PCT

    async def check_order(self, user_id: str, symbol: str, side: str, amount_usdt: float) -> tuple[bool, str]:
        if amount_usdt <= 0:
            return False, "Amount must be positive"
        if amount_usdt > self.max_position:
            return False, f"Order amount ${amount_usdt:.2f} exceeds max ${self.max_position:.2f}"

        async with async_session() as session:
            # Check daily loss
            today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
            result = await session.execute(
                select(func.coalesce(func.sum(Trade.profit), 0))
                .where(Trade.closed_at >= today_start)
            )
            daily_pnl = result.scalar() or 0
            if daily_pnl < 0 and abs(daily_pnl) > 0:
                from db.models import Portfolio
                port_result = await session.execute(
                    select(func.coalesce(func.sum(Portfolio.total_value), 10000))
                )
                total_value = port_result.scalar() or 10000
                loss_pct = abs(daily_pnl) / total_value * 100
                if loss_pct > self.max_daily_loss_pct:
                    return False, f"Daily loss {loss_pct:.1f}% exceeds limit {self.max_daily_loss_pct}%"

            # Check open orders count
            result = await session.execute(
                select(func.count(Order.id))
                .where(Order.user_id == user_id, Order.status == OrderStatus.OPEN)
            )
            open_count = result.scalar() or 0
            if open_count >= self.max_open_orders:
                return False, f"Open orders {open_count} exceeds limit {self.max_open_orders}"

        return True, ""


risk_manager = RiskManager()
