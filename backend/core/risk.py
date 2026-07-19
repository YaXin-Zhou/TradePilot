"""风险控制中间件"""
from config import settings


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
        return True, ""


risk_manager = RiskManager()
