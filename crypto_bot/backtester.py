"""Backtest del team di agenti su candele storiche reali di Coinbase (paper trading)."""
from __future__ import annotations

import pandas as pd

from .manager import ManagerAgent
from .portfolio import Portfolio


def run_backtest(candles: pd.DataFrame, manager: ManagerAgent, portfolio: Portfolio,
                  product: str, warmup: int = 25) -> dict:
    """Itera candela per candela (solo su barre già chiuse: nessun look-ahead)."""
    if len(candles) <= warmup:
        raise ValueError("Serie storica troppo corta per il warmup degli indicatori")

    for i in range(warmup, len(candles)):
        window = candles.iloc[: i + 1]
        ts = candles.index[i]
        price = float(candles["close"].iloc[i])

        stop_trade = portfolio.check_stop_and_target(product, price, ts)

        has_position = product in portfolio.positions
        decision = manager.decide(window, orderflow=None, has_position=has_position)

        if decision.action == "BUY" and not has_position:
            portfolio.buy(product, price, ts, reason=decision.reason)
        elif decision.action == "SELL" and has_position and portfolio.held_long_enough(product, ts):
            portfolio.sell(product, price, ts, reason=decision.reason)

        portfolio.record_equity(ts, {product: price})

    last_price = float(candles["close"].iloc[-1])
    if product in portfolio.positions:
        portfolio.sell(product, last_price, candles.index[-1], reason="chiusura fine backtest")
        portfolio.record_equity(candles.index[-1], {product: last_price})

    return portfolio.metrics({product: last_price})
