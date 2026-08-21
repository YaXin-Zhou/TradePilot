"""告警服务 — Telegram Bot / 通用 Webhook 双通道推送

支持事件：
  - 策略信号 (BUY/SELL)
  - 止损触发
  - 日 PnL 结单
  - Kill Switch 触发/解除
  - 对账差异
  - 日亏熔断
  - 策略 error / 心跳掉线

配置（.env）：
  TELEGRAM_BOT_TOKEN / TELEGRAM_CHAT_ID — Telegram 通道（任一为空则禁用）
  ALERT_WEBHOOK_URL — 通用 Webhook（POST JSON），Telegram 未配时可用

v6: 双通道 + 关键事件全量接入；发送失败仅告警不抛出，绝不阻塞交易主链路。
"""
import aiohttp
from core.logger import log
from config import settings


class AlertService:
    """统一告警服务（Telegram + Webhook 双通道）"""

    def __init__(self):
        self._telegram_token = settings.TELEGRAM_BOT_TOKEN
        self._telegram_chat_id = settings.TELEGRAM_CHAT_ID
        self._webhook_url = settings.ALERT_WEBHOOK_URL
        self._telegram_enabled = bool(self._telegram_token and self._telegram_chat_id)
        self._webhook_enabled = bool(self._webhook_url)

    @property
    def enabled(self) -> bool:
        """任一通道可用即视为告警可用"""
        return self._telegram_enabled or self._webhook_enabled

    @property
    def telegram_enabled(self) -> bool:
        return self._telegram_enabled

    @property
    def webhook_enabled(self) -> bool:
        return self._webhook_enabled

    async def send(self, message: str, title: str = "") -> bool:
        """向所有可用通道发送消息。任一通道成功即返回 True。"""
        if not self.enabled:
            return False
        ok = False
        if self._telegram_enabled:
            ok = await self._send_telegram(message) or ok
        if self._webhook_enabled:
            ok = await self._send_webhook(message, title) or ok
        return ok

    async def _send_telegram(self, message: str) -> bool:
        try:
            url = f"https://api.telegram.org/bot{self._telegram_token}/sendMessage"
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json={
                    "chat_id": self._telegram_chat_id,
                    "text": message,
                    "parse_mode": "HTML",
                }, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    if resp.status == 200:
                        log.info(f"Alert(telegram) sent: {message[:100]}")
                        return True
                    log.warning(f"Alert(telegram) failed: HTTP {resp.status}")
                    return False
        except Exception as e:
            log.warning(f"Alert(telegram) error: {e}")
            return False

    async def _send_webhook(self, message: str, title: str = "") -> bool:
        try:
            payload = {"title": title or "TradePilot Alert", "message": message}
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    self._webhook_url, json=payload,
                    timeout=aiohttp.ClientTimeout(total=10),
                ) as resp:
                    if resp.status in (200, 201, 204):
                        log.info(f"Alert(webhook) sent: {message[:100]}")
                        return True
                    log.warning(f"Alert(webhook) failed: HTTP {resp.status}")
                    return False
        except Exception as e:
            log.warning(f"Alert(webhook) error: {e}")
            return False

    # ------------------------------------------------------------------
    # 事件封装
    # ------------------------------------------------------------------

    async def signal(self, strategy_name: str, symbol: str, side: str, price: float, reason: str):
        side_emoji = "🟢" if side.upper() == "BUY" else "🔴"
        msg = f"{side_emoji} <b>{side.upper()}</b> {symbol}\n"
        msg += f"策略: {strategy_name}\n"
        msg += f"价格: ${price:.2f}\n"
        msg += f"原因: {reason}"
        await self.send(msg, title=f"Signal {side.upper()} {symbol}")

    async def stop_loss(self, strategy_name: str, symbol: str, loss_pct: float):
        msg = f"🛑 <b>止损触发</b> {symbol}\n"
        msg += f"策略: {strategy_name}\n"
        msg += f"亏损: {loss_pct:.2f}%"
        await self.send(msg, title=f"StopLoss {symbol}")

    async def daily_summary(self, pnl: float, trades: int, win_rate: float):
        emoji = "📈" if pnl >= 0 else "📉"
        msg = f"{emoji} <b>日结算</b>\n"
        msg += f"PnL: ${pnl:+.2f}\n"
        msg += f"交易: {trades} 笔\n"
        msg += f"胜率: {win_rate:.1f}%"
        await self.send(msg, title="Daily Summary")

    async def kill_switch_triggered(self, reason: str):
        msg = f"⚠️ <b>KILL SWITCH 触发</b>\n原因: {reason}"
        await self.send(msg, title="Kill Switch Triggered")

    async def kill_switch_reset(self):
        msg = "✅ <b>KILL SWITCH 已解除</b> — 交易恢复"
        await self.send(msg, title="Kill Switch Reset")

    async def daily_loss_breach(self, loss_usdt: float, limit_usdt: float):
        msg = f"🚨 <b>日亏熔断</b>\n"
        msg += f"当日亏损: ${loss_usdt:.2f}\n"
        msg += f"熔断线: ${limit_usdt:.2f}"
        await self.send(msg, title="Daily Loss Breach")

    async def reconcile_mismatch(self, issues: list[str]):
        lines = "\n".join(f"  - {i}" for i in issues[:10])
        msg = f"🔍 <b>对账差异</b> ({len(issues)} 项)\n{lines}"
        await self.send(msg, title="Reconcile Mismatch")

    async def strategy_error(self, strategy_name: str, error: str):
        msg = f"❌ <b>策略异常</b>\n策略: {strategy_name}\n错误: {error[:200]}"
        await self.send(msg, title="Strategy Error")

    async def heartbeat_offline(self, detail: str = ""):
        msg = f"📡 <b>心跳掉线</b>\n{detail}"
        await self.send(msg, title="Heartbeat Offline")


alert_service = AlertService()
