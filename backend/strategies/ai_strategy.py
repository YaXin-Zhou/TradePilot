"""AI Strategy Engine"""
import json
import httpx
import re
from typing import Optional
from strategies.base import Signal, SignalType


class AIStrategyEngine:
    """AI strategy engine using DeepSeek"""

    SYSTEM_PROMPT = "You are a quant analyst. Return JSON with signal (buy/sell/hold), confidence (0-1), reason."

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.deepseek.com/v1/chat/completions"

    async def analyze(self, strategy_desc: str, market_data: dict) -> Optional[Signal]:
        if not self.api_key:
            return Signal(type=SignalType.HOLD, price=0, reason="No API key")
        try:
            prompt = self._build_prompt(strategy_desc, market_data)
            result = await self._call_deepseek(prompt)
            return self._parse_response(result, market_data)
        except Exception as e:
            return Signal(type=SignalType.HOLD, price=0, reason=str(e)[:80])

    def _build_prompt(self, strategy_desc: str, data: dict) -> str:
        t = data.get("ticker", {})
        ind = data.get("indicators", {})
        return (
            f"Strategy: {strategy_desc}\n"
            f"Price: {t.get('last', 'N/A')}  Change: {t.get('change_pct', 'N/A')}%\n"
            f"RSI: {ind.get('rsi', 'N/A')}  MACD: {ind.get('macd', 'N/A')}\n"
            f"EMA9: {ind.get('ema_9', 'N/A')}  EMA21: {ind.get('ema_21', 'N/A')}\n"
            f"Return JSON with signal, confidence, reason"
        )

    async def _call_deepseek(self, prompt: str) -> dict:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "messages": [
                    {"role": "system", "content": self.SYSTEM_PROMPT},
                    {"role": "user", "content": prompt}
                ], "temperature": 0.3},
            )
            resp.raise_for_status()
            return resp.json()

    def _parse_response(self, raw: dict, market: dict) -> Signal:
        try:
            c = raw["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", c, re.DOTALL)
            data = json.loads(m.group()) if m else {}
            smap = {"buy": SignalType.BUY, "sell": SignalType.SELL, "hold": SignalType.HOLD}
            return Signal(
                type=smap.get(data.get("signal", "hold").lower(), SignalType.HOLD),
                price=market.get("last", 0),
                confidence=float(data.get("confidence", 0.5)),
                reason=data.get("reason", ""),
            )
        except Exception:
            return Signal(type=SignalType.HOLD, price=0, reason="Parse failed")

