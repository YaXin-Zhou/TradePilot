"""告警服务 — Telegram Bot 推送

支持事件：
  - 策略信号 (BUY/SELL)
  - 止损触发
  - 日 PnL 结单
  - Kill Switch 触发
"""
import aiohttp
from core.logger import log
from config import settings


class AlertService:
    """统一告警服务"""

    def __init__(self):
        self._token = settings.TELEGRAM_BOT_TOKEN
        self._chat_id = settings.TELEGRAM_CHAT_ID
        self._enabled = bool(self._token and self._chat_id)

    @property
    def enabled(self) -> bool:
        return self._enabled

    async def send(self, message: str) -> bool:
        """发送 Telegram 消息"""
        if not self._enabled:
            return False
        try:
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={
                    "chat_id": self._chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                }, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        log.info(f"Alert sent: {message[:100]}")
                        return True
                    log.warning(f"Alert failed: HTTP {resp.status}")
                    return False
        except Exception as e:
            log.warning(f"Alert send error: {e}")
            return False

    async def signal(self, strategy_name: str, symbol: str, side: str, price: float, reason: str):
        side_emoji = "🟢" if side.upper() == "BUY" else "🔴"
        msg = f"{side_emoji} <b>{side.upper()}</b> {symbol}\n"
        msg += f"策略: {strategy_name}\n"
        msg += f"价格: ${price:.2f}\n"
        msg += f"原因: {reason}"
        await self.send(msg)

    async def stop_loss(self, strategy_name: str, symbol: str, loss_pct: float):
        msg = f"🛑 <b>止损触发</b> {symbol}\n"
        msg += f"策略: {strategy_name}\n"
        msg += f"亏损: {loss_pct:.2f}%"
        await self.send(msg)

    async def daily_summary(self, pnl: float, trades: int, win_rate: float):
        emoji = "📈" if pnl >= 0 else "📉"
        msg = f"{emoji} <b>日结算</b>\n"
        msg += f"PnL: ${pnl:+.2f}\n"
        msg += f"交易: {trades} 笔\n"
        msg += f"胜率: {win_rate:.1f}%"
        await self.send(msg)

    async def kill_switch_triggered(self, reason: str):
        msg = f"⚠️ <b>KILL SWITCH 触发</b>\n原因: {reason}"
        await self.send(msg)


alert_service = AlertService()
