"""AI Strategy Engine"""
import json
import httpx
import re
from typing import Optional
from strategies.base import Signal, SignalType


class AIStrategyEngine:
    """AI strategy engine using DeepSeek"""

    SYSTEM_PROMPT = """You are a quant trading strategist. Analyze market data and return JSON with:
- signal: buy/sell/hold/strong_buy/strong_sell
- confidence: 0-1
- reason: brief explanation
- strategy_type: one of "ma_crossover", "rsi", "bollinger"
- strategy_params: object with parameters for that strategy

For ma_crossover: {"fast": int, "slow": int}
For rsi: {"period": int, "oversold": int, "overbought": int}
For bollinger: {"period": int, "std_dev": float}"""

    AUTO_SYSTEM_PROMPT = """You are a quant trading strategist examining live market data. Automatically determine the best strategy.

Return JSON with:
- market_assessment: brief summary of current market conditions
- strategy_description: clear human-readable description of your recommended strategy
- signal: buy/sell/hold/strong_buy/strong_sell
- confidence: 0-1
- reason: detailed reasoning based on indicators
- strategy_type: one of ma_crossover, rsi, bollinger
- strategy_params: parameters for that strategy

Analyze ALL indicators. Consider trend, momentum, volatility, volume."""

    def __init__(self, api_key: str, model: str = "deepseek-chat"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.deepseek.com/v1/chat/completions"

    async def auto_analyze(self, market_data: dict) -> tuple[Optional[Signal], dict]:
        """Auto-analyze market data, generate and backtest strategy"""
        if not self.api_key:
            return Signal(type=SignalType.HOLD, price=0, reason="No API key"), {}
        try:
            prompt = self._build_auto_prompt(market_data)
            result = await self._call_deepseek(prompt, self.AUTO_SYSTEM_PROMPT)
            return self._parse_response(result, market_data)
        except Exception as e:
            return Signal(type=SignalType.HOLD, price=0, reason=str(e)[:80]), {}

    async def analyze(self, strategy_desc: str, market_data: dict) -> tuple[Optional[Signal], dict]:
        if not self.api_key:
            return Signal(type=SignalType.HOLD, price=0, reason="No API key"), {}
        try:
            prompt = self._build_prompt(strategy_desc, market_data)
            result = await self._call_deepseek(prompt)
            return self._parse_response(result, market_data)
        except Exception as e:
            return Signal(type=SignalType.HOLD, price=0, reason=str(e)[:80]), {}

    def _build_prompt(self, strategy_desc: str, data: dict) -> str:
        t = data.get("ticker", {})
        ind = data.get("indicators", {})
        return (
            f"Strategy: {strategy_desc}\n"
            f"Price: {t.get('last', 'N/A')}  Change: {t.get('change_pct', 'N/A')}%\n"
            f"RSI: {ind.get('rsi', 'N/A')}  MACD: {ind.get('macd', 'N/A')}\n"
            f"EMA9: {ind.get('ema_9', 'N/A')}  EMA21: {ind.get('ema_21', 'N/A')}\n"
            f"Return JSON with signal, confidence, reason, strategy_type, strategy_params"
        )

    def _build_auto_prompt(self, data: dict) -> str:
        t = data.get("ticker", {})
        ind = data.get("indicators", {})
        return (
            f"Current Market Data:\n"
            f"Price: {t.get('last', 'N/A')}  24h Change: {t.get('change_pct', 'N/A')}%\n"
            f"Volume: {t.get('volume', 'N/A')}\n"
            f"\nTechnical Indicators:\n"
            f"RSI(14): {ind.get('rsi', 'N/A')}\n"
            f"MACD: {ind.get('macd', 'N/A')}  Signal: {ind.get('macd_signal', 'N/A')}\n"
            f"BB Upper: {ind.get('bb_upper', 'N/A')}  Lower: {ind.get('bb_lower', 'N/A')}\n"
            f"EMA 9/21/50: {ind.get('ema_9', 'N/A')} / {ind.get('ema_21', 'N/A')} / {ind.get('ema_50', 'N/A')}\n"
            f"Volume Ratio: {ind.get('volume_ratio', 'N/A')}\n"
            f"\nDetermine the best strategy based on this data and return JSON."
        )

    async def _call_deepseek(self, prompt: str, system_prompt: Optional[str] = None) -> dict:
        sp = system_prompt or self.SYSTEM_PROMPT
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                self.api_url,
                headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                json={"model": self.model, "messages": [
                    {"role": "system", "content": sp},
                    {"role": "user", "content": prompt}
                ], "temperature": 0.3},
            )
            resp.raise_for_status()
            return resp.json()

    def _parse_response(self, raw: dict, market: dict) -> tuple[Signal, dict]:
        strategy_info = {"type": "", "params": {}}
        try:
            c = raw["choices"][0]["message"]["content"]
            m = re.search(r"\{.*\}", c, re.DOTALL)
            if not m:
                return Signal(type=SignalType.HOLD, price=0, reason="Parse failed"), strategy_info
            data = json.loads(m.group())
            smap = {"buy": SignalType.BUY, "sell": SignalType.SELL, "hold": SignalType.HOLD, "strong_buy": SignalType.STRONG_BUY, "strong_sell": SignalType.STRONG_SELL}
            signal = Signal(
                type=smap.get(data.get("signal", "hold").lower(), SignalType.HOLD),
                price=market.get("last", 0),
                confidence=float(data.get("confidence", 0.5)),
                reason=data.get("reason", ""),
            )
            strategy_info = {
                "type": data.get("strategy_type", "ma_crossover"),
                "params": data.get("strategy_params", {}),
                "strategy_description": data.get("strategy_description", ""),
                "market_assessment": data.get("market_assessment", ""),
            }
            return signal, strategy_info
        except Exception:
            return Signal(type=SignalType.HOLD, price=0, reason="Parse failed"), strategy_info
