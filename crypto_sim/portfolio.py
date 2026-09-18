"""Long-only virtual portfolio with fees, stop-loss, take-profit."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from crypto_sim.config import (
    DEFAULT_CASH,
    DEFAULT_FEE_RATE,
    DEFAULT_POSITION_FRACTION,
    DEFAULT_STOP_LOSS_PCT,
    DEFAULT_TAKE_PROFIT_PCT,
)
from crypto_sim.manager import Decision


@dataclass
class Trade:
    entry_time: object
    exit_time: object
    entry_price: float
    exit_price: float
    size: float
    pnl: float
    return_pct: float
    reason: str  # signal / stop_loss / take_profit / end_of_data


@dataclass
class Portfolio:
    cash: float = DEFAULT_CASH
    fee_rate: float = DEFAULT_FEE_RATE
    position_fraction: float = DEFAULT_POSITION_FRACTION
    stop_loss_pct: float = DEFAULT_STOP_LOSS_PCT
    take_profit_pct: float = DEFAULT_TAKE_PROFIT_PCT

    position: float = 0.0
    entry_price: float = 0.0
    entry_cash_out: float = 0.0
    entry_time: object = None
    equity_curve: List[float] = field(default_factory=list)
    trades: List[Trade] = field(default_factory=list)
    initial_cash: float = field(init=False)

    def __post_init__(self):
        self.initial_cash = self.cash

    @property
    def in_position(self) -> bool:
        return self.position > 0

    def mark_to_market(self, price: float) -> float:
        return self.cash + self.position * price

    def check_stops(self, high: float, low: float, time) -> Optional[Trade]:
        """Stop-loss / take-profit via bar high/low. If both, SL first (pessimistic)."""
        if not self.in_position:
            return None
        sl = self.entry_price * (1.0 - self.stop_loss_pct)
        tp = self.entry_price * (1.0 + self.take_profit_pct)
        if low <= sl:
            return self._close(sl, time, "stop_loss")
        if high >= tp:
            return self._close(tp, time, "take_profit")
        return None

    def apply_decision(self, decision: Decision, price: float, time) -> Optional[Trade]:
        """Execute at fill price (typically next-bar open)."""
        if decision == Decision.BUY and not self.in_position and self.cash > 0:
            budget = self.cash * self.position_fraction
            fee = budget * self.fee_rate
            spend = budget - fee
            if spend <= 0 or price <= 0:
                return None
            self.position = spend / price
            self.cash -= budget
            self.entry_price = price
            self.entry_cash_out = budget
            self.entry_time = time
            return None
        if decision == Decision.SELL and self.in_position:
            return self._close(price, time, "signal")
        return None

    def _close(self, price: float, time, reason: str) -> Trade:
        gross = self.position * price
        fee = gross * self.fee_rate
        proceeds = gross - fee
        pnl = proceeds - self.entry_cash_out
        ret = pnl / self.entry_cash_out if self.entry_cash_out else 0.0
        trade = Trade(
            entry_time=self.entry_time,
            exit_time=time,
            entry_price=self.entry_price,
            exit_price=price,
            size=self.position,
            pnl=pnl,
            return_pct=ret * 100.0,
            reason=reason,
        )
        self.cash += proceeds
        self.position = 0.0
        self.entry_price = 0.0
        self.entry_cash_out = 0.0
        self.entry_time = None
        self.trades.append(trade)
        return trade

    def force_close(self, price: float, time) -> Optional[Trade]:
        if self.in_position:
            return self._close(price, time, "end_of_data")
        return None

    def record_equity(self, price: float) -> None:
        self.equity_curve.append(self.mark_to_market(price))
