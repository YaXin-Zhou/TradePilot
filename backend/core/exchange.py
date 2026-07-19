"""
OKX 交易所客户端 - 基于 CCXT 封装
"""
import ccxt
import pandas as pd
import os
import time
from typing import Optional


# Global connectivity flag (shared across instances)
_connected: bool = True  # NOTE: managed by ExchangeClient._connected now


def set_connected(value: bool):
    global _connected
    _connected = value


class ExchangeError(Exception):
    pass


class ExchangeClient:
    """统一交易所接口，默认 OKX"""

    def __init__(
        self,
        exchange_name: str = "okx",
        api_key: str = "",
        secret: str = "",
        passphrase: str = "",
        testnet: bool = True,
    ):
        exchange_class = getattr(ccxt, exchange_name)
        params = {
            "enableRateLimit": True,
        "timeout": 8000,
            "options": {"defaultType": "spot"},
        }
        # Auto-detect proxy from env vars
        proxy_url = (
            settings.HTTPS_PROXY or settings.HTTP_PROXY or
            os.environ.get("HTTPS_PROXY") or os.environ.get("HTTP_PROXY") or
            os.environ.get("https_proxy") or os.environ.get("http_proxy") or
            ""
        )
        if proxy_url:
            params["proxies"] = {"http": proxy_url, "https": proxy_url}
            params["timeout"] = 10000
        if api_key and secret:
            params["apiKey"] = api_key
            params["secret"] = secret
            if passphrase:
                params["password"] = passphrase

        self._exchange = exchange_class(params)
        if testnet:
            try:
                self._exchange.set_sandbox_mode(True)
            except Exception:
                pass
        self._markets_loaded = False
        self._testnet = testnet
        self._connected = False
        self._name = exchange_name
        self._last_attempt = time.time()
        self._retry_interval = 60


    def _ensure_markets(self):
        if not self._markets_loaded:
            try:
                self._exchange.load_markets()
                self._markets_loaded = True
                self._connected = False
            except Exception:
                self._last_attempt = time.time()
                self._markets_loaded = False

    def _try_reconnect(self):
        if self._connected:
            return True
        if time.time() - self._last_attempt > self._retry_interval:
            try:
                self._exchange.load_markets()
                self._markets_loaded = True
                self._connected = True
                return True
            except Exception:
                self._last_attempt = time.time()
        return self._connected

    @property
    def name(self) -> str:
        return self._name

    @property
    def is_testnet(self) -> bool:
        return self._testnet

    def fetch_ticker(self, symbol: str) -> dict:
        self._try_reconnect()
        if not self._connected:
            raise ConnectionError("offline")
        try:
            t = self._exchange.fetch_ticker(symbol)
            self._connected = False
            return {
                "symbol": symbol,
                "bid": float(t.get("bid", 0)),
                "ask": float(t.get("ask", 0)),
                "last": float(t.get("last", 0)),
                "high": float(t.get("high", 0)),
                "low": float(t.get("low", 0)),
                "volume": float(t.get("baseVolume", 0)),
                "quote_volume": float(t.get("quoteVolume", 0)),
                "change_pct": float(t.get("percentage", 0)),
                "timestamp": t.get("timestamp", 0),
            }
        except Exception as e:
            self._connected = False
            self._last_attempt = time.time()
            raise ConnectionError(f"offline: {e}")

    def fetch_ohlcv(self, symbol: str, timeframe: str = "1h", limit: int = 200):
        self._try_reconnect()
        if not self._connected:
            raise ConnectionError("offline")
        ohlcv = self._exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(
            ohlcv,
            columns=["timestamp", "open", "high", "low", "close", "volume"],
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
        df["symbol"] = symbol
        return df

    def fetch_orderbook(self, symbol: str, limit: int = 20) -> dict:
        self._try_reconnect()
        if not self._connected:
            raise ConnectionError("offline")
        ob = self._exchange.fetch_order_book(symbol, limit)
        return {
            "bids": [[float(p), float(v)] for p, v in ob.get("bids", [])],
            "asks": [[float(p), float(v)] for p, v in ob.get("asks", [])],
            "timestamp": ob.get("timestamp", 0),
        }

    def fetch_balance(self, currency: Optional[str] = None) -> dict:
        self._ensure_markets()
        self._try_reconnect()
        if not self._connected:
            raise ConnectionError('offline')
        bal = self._exchange.fetch_balance()
        if currency:
            c = bal.get(currency, {})
            return {
                "currency": currency,
                "free": float(c.get("free", 0) or 0),
                "used": float(c.get("used", 0) or 0),
                "total": float(c.get("total", 0) or 0),
            }
        result = {}
        for cur, _ in bal.get("total", {}).items():
            total = float(bal.get(cur, {}).get("total", 0) or 0)
            if total > 0:
                result[cur] = {
                    "free": float(bal.get(cur, {}).get("free", 0) or 0),
                    "used": float(bal.get(cur, {}).get("used", 0) or 0),
                    "total": total,
                }
        return result

    def _to_price(self, symbol: str, price: float) -> float:
        self._ensure_markets()
        return float(self._exchange.price_to_precision(symbol, price))

    def _to_amount(self, symbol: str, amount: float) -> float:
        self._ensure_markets()
        return float(self._exchange.amount_to_precision(symbol, amount))

    def create_limit_order(self, symbol: str, side: str, amount: float, price: float) -> Optional[dict]:
        self._ensure_markets()
        price = self._to_price(symbol, price)
        amount = self._to_amount(symbol, amount)
        try:
            order = self._exchange.create_limit_order(symbol, side, amount, price)
            return {
                "id": order.get("id"),
                "symbol": symbol,
                "side": side,
                "price": float(order.get("price", price)),
                "amount": float(order.get("amount", amount)),
                "filled": float(order.get("filled", 0)),
                "cost": float(order.get("cost", 0)),
                "status": order.get("status", "open"),
                "timestamp": order.get("timestamp"),
            }
        except Exception as e:
            raise ExchangeError(f"下单失败: {e}")

    def create_market_order(self, symbol: str, side: str, amount: float) -> Optional[dict]:
        self._ensure_markets()
        try:
            order = self._exchange.create_market_order(symbol, side, amount)
            return {
                "id": order.get("id"),
                "symbol": symbol,
                "side": side,
                "price": float(order.get("price", 0)),
                "amount": float(order.get("amount", amount)),
                "filled": float(order.get("filled", 0)),
                "cost": float(order.get("cost", 0)),
                "status": order.get("status", "closed"),
                "timestamp": order.get("timestamp"),
            }
        except Exception as e:
            raise ExchangeError(f"市价单失败: {e}")

    def fetch_order(self, order_id: str, symbol: str) -> Optional[dict]:
        self._ensure_markets()
        try:
            o = self._exchange.fetch_order(order_id, symbol)
            return {
                "id": o.get("id"),
                "symbol": symbol,
                "side": o.get("side"),
                "price": float(o.get("price", 0)),
                "amount": float(o.get("amount", 0)),
                "filled": float(o.get("filled", 0)),
                "cost": float(o.get("cost", 0)),
                "status": o.get("status"),
                "timestamp": o.get("timestamp"),
            }
        except Exception:
            return None

    def cancel_order(self, order_id: str, symbol: str) -> bool:
        try:
            self._exchange.cancel_order(order_id, symbol)
            return True
        except Exception:
            return False

    def fetch_open_orders(self, symbol: str) -> list[dict]:
        self._ensure_markets()
        try:
            orders = self._exchange.fetch_open_orders(symbol)
            return [
                {
                    "id": o.get("id"),
                    "side": o.get("side"),
                    "price": float(o.get("price", 0)),
                    "amount": float(o.get("amount", 0)),
                    "filled": float(o.get("filled", 0)),
                    "status": o.get("status"),
                }
                for o in orders
            ]
        except Exception:
            return []

    def fetch_my_trades(self, symbol: str, limit: int = 50) -> list[dict]:
        self._ensure_markets()
        try:
            trades = self._exchange.fetch_my_trades(symbol, limit=limit)
            return [
                {
                    "id": t.get("id"),
                    "side": t.get("side"),
                    "price": float(t.get("price", 0)),
                    "amount": float(t.get("amount", 0)),
                    "cost": float(t.get("cost", 0)),
                    "fee": float(t.get("fee", {}).get("cost", 0)) if t.get("fee") else 0,
                    "timestamp": t.get("timestamp"),
                }
                for t in trades
            ]
        except Exception:
            return []

# Single shared exchange instance for all API modules
from config import settings

shared_exchange = ExchangeClient(
    exchange_name=settings.EXCHANGE_NAME,
    api_key=settings.EXCHANGE_API_KEY,
    secret=settings.EXCHANGE_SECRET,
    passphrase=settings.EXCHANGE_PASSPHRASE,
    testnet=settings.EXCHANGE_TESTNET,
)

