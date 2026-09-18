"""Portafoglio virtuale (paper trading): nessun ordine reale, solo simulazione."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd


@dataclass
class Position:
    qty: float
    avg_price: float
    stop_loss: Optional[float] = None
    take_profit: Optional[float] = None


class Portfolio:
    def __init__(self, starting_cash: float = 10_000.0, fee_rate: float = 0.006,
                 max_position_pct: float = 0.20, stop_loss_pct: float = 0.015,
                 take_profit_pct: float = 0.03):
        self.starting_cash = starting_cash
        self.cash = starting_cash
        self.fee_rate = fee_rate
        self.max_position_pct = max_position_pct
        self.stop_loss_pct = stop_loss_pct
        self.take_profit_pct = take_profit_pct
        self.positions: dict[str, Position] = {}
        self.trade_log: list[dict] = []
        self.equity_curve: list[dict] = []

    def equity(self, prices: dict[str, float]) -> float:
        total = self.cash
        for product, pos in self.positions.items():
            price = prices.get(product, pos.avg_price)
            total += pos.qty * price
        return total

    def can_buy(self, product: str) -> bool:
        return product not in self.positions and self.cash > 1.0

    def buy(self, product: str, price: float, timestamp, reason: str = "") -> Optional[dict]:
        if not self.can_buy(product) or price <= 0 or not np.isfinite(price):
            return None
        budget = self.cash * self.max_position_pct
        if budget < 1.0:
            return None
        fee = budget * self.fee_rate
        qty = (budget - fee) / price
        if qty <= 0:
            return None
        self.cash -= budget
        self.positions[product] = Position(
            qty=qty, avg_price=price,
            stop_loss=price * (1 - self.stop_loss_pct),
            take_profit=price * (1 + self.take_profit_pct),
        )
        trade = {"timestamp": timestamp, "product": product, "side": "BUY",
                  "price": price, "qty": qty, "fee": fee, "reason": reason}
        self.trade_log.append(trade)
        return trade

    def sell(self, product: str, price: float, timestamp, reason: str = "") -> Optional[dict]:
        pos = self.positions.get(product)
        if pos is None or price <= 0 or not np.isfinite(price):
            return None
        proceeds = pos.qty * price
        fee = proceeds * self.fee_rate
        pnl = (price - pos.avg_price) * pos.qty - fee
        pnl_pct = (price / pos.avg_price - 1) * 100
        self.cash += proceeds - fee
        del self.positions[product]
        trade = {"timestamp": timestamp, "product": product, "side": "SELL",
                  "price": price, "qty": pos.qty, "fee": fee,
                  "pnl": pnl, "pnl_pct": pnl_pct, "reason": reason}
        self.trade_log.append(trade)
        return trade

    def check_stop_and_target(self, product: str, price: float, timestamp) -> Optional[dict]:
        """Stop-loss / take-profit automatici — la reazione più rapida che il portafoglio
        può avere a una candela che sta girando, indipendentemente dagli agenti."""
        pos = self.positions.get(product)
        if pos is None:
            return None
        if pos.stop_loss and price <= pos.stop_loss:
            return self.sell(product, price, timestamp, reason="stop-loss")
        if pos.take_profit and price >= pos.take_profit:
            return self.sell(product, price, timestamp, reason="take-profit")
        return None

    def record_equity(self, timestamp, prices: dict[str, float]):
        self.equity_curve.append({"timestamp": timestamp, "equity": self.equity(prices)})

    def metrics(self, prices: dict[str, float]) -> dict:
        eq = self.equity(prices)
        closed = [t for t in self.trade_log if t["side"] == "SELL"]
        wins = [t for t in closed if t.get("pnl", 0) > 0]
        eq_series = pd.Series([e["equity"] for e in self.equity_curve]) if self.equity_curve else pd.Series([eq])
        running_max = eq_series.cummax()
        drawdown = ((eq_series - running_max) / running_max).min() if len(eq_series) else 0.0
        return {
            "equity": eq,
            "total_return_pct": (eq / self.starting_cash - 1) * 100,
            "num_trades": len(closed),
            "win_rate_pct": (len(wins) / len(closed) * 100) if closed else 0.0,
            "max_drawdown_pct": float(drawdown * 100) if np.isfinite(drawdown) else 0.0,
            "open_positions": len(self.positions),
            "cash": self.cash,
        }
