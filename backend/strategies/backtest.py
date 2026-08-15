"""回测引擎 - 支持多种策略的历史模拟交易"""
import pandas as pd
import numpy as np
from datetime import datetime
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class BacktestTrade:
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    side: str = "buy"
    size: float = 0.0
    pnl: float = 0.0
    pnl_pct: float = 0.0
    fee: float = 0.0
    status: str = "open"


@dataclass
class BacktestResult:
    symbol: str
    timeframe: str
    bars: int
    strategy_name: str
    strategy_params: dict
    initial_capital: float
    final_capital: float
    total_return: float
    total_return_pct: float
    sharpe_ratio: float
    max_drawdown: float
    max_drawdown_pct: float
    win_rate: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    sortino_ratio: float = 0.0  # v2.0: quantstats 计算
    avg_win: float = 0.0
    avg_loss: float = 0.0
    profit_factor: float = 0.0
    total_fees: float = 0.0
    trades: list = field(default_factory=list)
    equity_curve: list = field(default_factory=list)


class BacktestEngine:
    def __init__(self, data: pd.DataFrame, initial_capital: float = 10000.0,
                 position_size_pct: float = 0.95,
                 trading_fee_pct: float = 0.001,
                 slippage_pct: float = 0.001):
        self.data = data.copy().reset_index(drop=True)
        self.initial_capital = initial_capital
        self.capital = initial_capital
        self.position = 0.0
        self.position_size_pct = position_size_pct
        self.trading_fee_pct = trading_fee_pct
        self.slippage_pct = slippage_pct
        self.trades: list[BacktestTrade] = []
        self.equity_curve: list[dict] = []
        self.total_fees: float = 0.0
        self._current_trade: Optional[BacktestTrade] = None

    def _record_equity(self, timestamp, price):
        eq_val = self.capital + (self.position * price)
        ts_str = timestamp.isoformat() if hasattr(timestamp, "isoformat") else str(timestamp)
        self.equity_curve.append({
            "timestamp": ts_str, "equity": round(eq_val, 2), "price": round(price, 2),
        })

    def _open_long(self, timestamp, price):
        entry_price = price * (1 + self.slippage_pct)  # slippage: buy higher
        cost = self.capital * self.position_size_pct
        fee = cost * self.trading_fee_pct
        size = (cost - fee) / entry_price
        self.position += size
        self.capital -= cost
        self.total_fees += fee
        trade = BacktestTrade(entry_time=timestamp, entry_price=entry_price, side="buy", size=size, fee=fee)
        self._current_trade = trade
        self.trades.append(trade)

    def _close_long(self, timestamp, price):
        if self._current_trade and self.position > 0:
            exit_price = price * (1 - self.slippage_pct)  # slippage: sell lower
            gross_proceeds = self.position * exit_price
            fee = gross_proceeds * self.trading_fee_pct
            net_proceeds = gross_proceeds - fee
            self._current_trade.exit_time = timestamp
            self._current_trade.exit_price = exit_price
            self._current_trade.fee = (self._current_trade.fee or 0) + fee
            self._current_trade.pnl = net_proceeds - (self.position * self._current_trade.entry_price)
            self._current_trade.pnl_pct = ((exit_price - self._current_trade.entry_price) / self._current_trade.entry_price) * 100
            self._current_trade.status = "closed"
            self.capital += net_proceeds
            self.total_fees += fee
            self.position = 0.0
            self._current_trade = None

    def run_ma_crossover(self, fast_period: int = 10, slow_period: int = 30) -> BacktestResult:
        df = self.data.copy()
        df["fast_ma"] = df["close"].rolling(fast_period).mean()
        df["slow_ma"] = df["close"].rolling(slow_period).mean()
        df["signal"] = 0
        df.loc[df["fast_ma"] > df["slow_ma"], "signal"] = 1
        df.loc[df["fast_ma"] < df["slow_ma"], "signal"] = -1
        # v2.0: 消除前视偏差 — 信号用前一根 K 线，成交用当前 K 线
        df["signal"] = df["signal"].shift(1).fillna(0).astype(int)
        df = df.dropna().reset_index(drop=True)
        for i in range(len(df)):
            row = df.iloc[i]
            price = float(row["close"])
            ts = row["timestamp"]
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()
            signal = int(row["signal"])
            prev_signal = int(df.iloc[i - 1]["signal"]) if i > 0 else 0
            self._record_equity(ts, price)
            if signal != prev_signal:
                if signal == 1 and self.position == 0:
                    self._open_long(ts, price)
                elif signal == -1 and self.position > 0:
                    self._close_long(ts, price)
        if self.position > 0:
            last = df.iloc[-1]
            self._close_long(last["timestamp"], float(last["close"]))
        return self._build_result(df, "MA Crossover", {"fast": fast_period, "slow": slow_period})

    def run_rsi(self, period: int = 14, oversold: int = 30, overbought: int = 70) -> BacktestResult:
        df = self.data.copy()
        delta = df["close"].diff()
        gain = delta.clip(lower=0)
        loss = (-delta).clip(lower=0)
        avg_g = gain.rolling(period).mean()
        avg_l = loss.rolling(period).mean()
        rs = avg_g / avg_l
        df["rsi"] = 100 - (100 / (1 + rs))
        # v2.0: 消除前视偏差 — RSI 用前一根 K 线
        df["rsi"] = df["rsi"].shift(1)
        df = df.dropna().reset_index(drop=True)
        for i in range(len(df)):
            row = df.iloc[i]
            price = float(row["close"])
            ts = row["timestamp"]
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()
            rsi = float(row["rsi"])
            self._record_equity(ts, price)
            if rsi < oversold and self.position == 0:
                self._open_long(ts, price)
            elif rsi > overbought and self.position > 0:
                self._close_long(ts, price)
        if self.position > 0:
            last = df.iloc[-1]
            self._close_long(last["timestamp"], float(last["close"]))
        return self._build_result(df, "RSI Mean Reversion", {"period": period, "oversold": oversold, "overbought": overbought})

    def run_bollinger(self, period: int = 20, std_dev: float = 2.0) -> BacktestResult:
        df = self.data.copy()
        df["sma"] = df["close"].rolling(period).mean()
        df["std"] = df["close"].rolling(period).std()
        df["upper"] = df["sma"] + std_dev * df["std"]
        df["lower"] = df["sma"] - std_dev * df["std"]
        # v2.0: 消除前视偏差 — 布林带用前一根 K 线
        df["upper"] = df["upper"].shift(1)
        df["lower"] = df["lower"].shift(1)
        df = df.dropna().reset_index(drop=True)
        for i in range(len(df)):
            row = df.iloc[i]
            price = float(row["close"])
            ts = row["timestamp"]
            if hasattr(ts, "to_pydatetime"):
                ts = ts.to_pydatetime()
            lo = float(row["lower"])
            hi = float(row["upper"])
            self._record_equity(ts, price)
            if price <= lo and self.position == 0:
                self._open_long(ts, price)
            elif price >= hi and self.position > 0:
                self._close_long(ts, price)
        if self.position > 0:
            last = df.iloc[-1]
            self._close_long(last["timestamp"], float(last["close"]))
        return self._build_result(df, "Bollinger Bands", {"period": period, "std_dev": std_dev})

    def _build_result(self, df, strategy_name: str, strategy_params: dict) -> BacktestResult:
        closed = [t for t in self.trades if t.status == "closed"]
        winning = [t for t in closed if t.pnl > 0]
        losing = [t for t in closed if t.pnl <= 0]
        n = len(closed)
        win_rate = len(winning) / n * 100 if n > 0 else 0
        avg_win = np.mean([t.pnl for t in winning]) if winning else 0
        avg_loss = abs(np.mean([t.pnl for t in losing])) if losing else 0
        pf = (sum(t.pnl for t in winning) / abs(sum(t.pnl for t in losing))
              if losing and abs(sum(t.pnl for t in losing)) > 0 else 999.99)
        total_return = self.capital - self.initial_capital
        total_return_pct = (total_return / self.initial_capital) * 100
        sharpe, sortino, max_dd, max_dd_pct = 0.0, 0.0, 0.0, 0.0
        if self.equity_curve:
            eq_vals = [e["equity"] for e in self.equity_curve]
            eq_series = pd.Series(eq_vals)
            rets = eq_series.pct_change().dropna()
            if len(rets) > 0:
                # v2.0: 用 quantstats 成熟库计算（1h K 线，年化周期 = 24*365）
                try:
                    import quantstats as qs
                    sharpe = round(float(qs.stats.sharpe(rets, periods=24 * 365)), 2)
                    sortino = round(float(qs.stats.sortino(rets, periods=24 * 365)), 2)
                except Exception:
                    sharpe = round(float(rets.mean() / rets.std() * np.sqrt(24 * 365)), 2) if rets.std() > 0 else 0
            peak = eq_series.expanding().max()
            dd = eq_series - peak
            dd_pct = dd / peak * 100
            max_dd = abs(float(dd.min())) if len(dd) > 0 else 0
            max_dd_pct = abs(float(dd_pct.min())) if len(dd_pct) > 0 else 0
        return BacktestResult(
            symbol=str(df.iloc[0].get("symbol", "BTC/USDT")),
            timeframe="1h", bars=len(df),
            strategy_name=strategy_name,
            strategy_params=strategy_params,
            initial_capital=self.initial_capital,
            final_capital=round(self.capital, 2),
            total_return=round(total_return, 2),
            total_return_pct=round(total_return_pct, 2),
            sharpe_ratio=sharpe,
            sortino_ratio=sortino,
            max_drawdown=round(max_dd, 2),
            max_drawdown_pct=round(max_dd_pct, 2),
            win_rate=round(win_rate, 2),
            total_trades=n, winning_trades=len(winning),
            losing_trades=len(losing),
            avg_win=round(avg_win, 2),
            avg_loss=round(avg_loss, 2),
            profit_factor=pf,
            total_fees=round(self.total_fees, 2),
            trades=[t.__dict__ for t in closed],
            equity_curve=self.equity_curve,
        )
