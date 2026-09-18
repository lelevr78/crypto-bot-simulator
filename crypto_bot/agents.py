"""Team of trading agents.

Each agent looks at the same OHLCV history (the last row may be a still-forming
/ partial candle — that's what lets the ensemble react before a bar closes)
and optionally at live order-flow stats, and returns a Signal:

    score   float in [-1, +1]   -1 = strong sell, 0 = neutral, +1 = strong buy
    reason  short human-readable explanation

The ManagerAgent (see manager.py) combines all of them into one decision.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

import numpy as np
import pandas as pd

from . import indicators as ind


@dataclass
class Signal:
    agent: str
    score: float
    reason: str
    available: bool = True  # False = nessun dato per questo agente (va escluso dal voto, non contato come neutro)


def _clip(x: float) -> float:
    if x is None or not np.isfinite(x):
        return 0.0
    return float(max(-1.0, min(1.0, x)))


class BaseAgent:
    name = "base"
    min_bars = 5

    def signal(self, df: pd.DataFrame, orderflow: Optional[dict] = None) -> Signal:
        if len(df) < self.min_bars:
            return Signal(self.name, 0.0, "storico insufficiente")
        return self._compute(df, orderflow)

    def _compute(self, df: pd.DataFrame, orderflow: Optional[dict]) -> Signal:
        raise NotImplementedError


class MomentumAgent(BaseAgent):
    """EMA crossover + rate of change: segue il trend a breve termine."""

    name = "Momentum"
    min_bars = 22

    def _compute(self, df, orderflow):
        close = df["close"]
        ema_fast = ind.ema(close, 9).iloc[-1]
        ema_slow = ind.ema(close, 21).iloc[-1]
        change5 = ind.roc(close, 5).iloc[-1]
        if not np.isfinite(ema_fast) or not np.isfinite(ema_slow):
            return Signal(self.name, 0.0, "EMA non ancora pronte")
        spread_pct = (ema_fast - ema_slow) / ema_slow * 100
        score = _clip(spread_pct * 0.6 + (change5 or 0) * 0.15)
        direction = "rialzista" if score > 0 else "ribassista" if score < 0 else "piatto"
        return Signal(self.name, score, f"trend {direction} (EMA9-21={spread_pct:.2f}%, ROC5={change5:.2f}%)")


class RSIReversionAgent(BaseAgent):
    """Contrarian: compra ipervenduto, vende ipercomprato."""

    name = "MeanReversion"
    min_bars = 16

    def _compute(self, df, orderflow):
        r = ind.rsi(df["close"], 14).iloc[-1]
        if r >= 70:
            score = _clip(-(r - 70) / 15)
            reason = f"RSI {r:.0f} ipercomprato"
        elif r <= 30:
            score = _clip((30 - r) / 15)
            reason = f"RSI {r:.0f} ipervenduto"
        else:
            score = 0.0
            reason = f"RSI {r:.0f} neutro"
        return Signal(self.name, score, reason)


class BollingerBreakoutAgent(BaseAgent):
    """Rottura delle bande di Bollinger: momentum di breakout."""

    name = "Breakout"
    min_bars = 22

    def _compute(self, df, orderflow):
        close = df["close"]
        upper, mid, lower = ind.bollinger(close, 20, 2.0)
        u, m, l, c = upper.iloc[-1], mid.iloc[-1], lower.iloc[-1], close.iloc[-1]
        if not np.isfinite(u) or not np.isfinite(l) or u == l:
            return Signal(self.name, 0.0, "bande non pronte")
        pos = (c - m) / ((u - l) / 2)  # -1..+1 circa dentro le bande, oltre se breakout
        score = _clip(pos * 0.8)
        reason = f"prezzo a {pos:+.2f} bande-sigma dalla media mobile"
        return Signal(self.name, score, reason)


class OrderFlowAgent(BaseAgent):
    """Anticipatorio: legge aggressività dei trade e sbilanciamento dell'order book
    PRIMA che la candela chiuda, per provare a entrare/uscire in anticipo."""

    name = "OrderFlow"
    min_bars = 1

    def _compute(self, df, orderflow):
        if not orderflow:
            return Signal(self.name, 0.0, "nessun dato order-flow live (es. backtest storico)", available=False)
        buy_v = orderflow.get("buy_volume", 0.0)
        sell_v = orderflow.get("sell_volume", 0.0)
        book_imb = orderflow.get("book_imbalance", 0.0)
        total = buy_v + sell_v
        trade_imb = (buy_v - sell_v) / total if total > 0 else 0.0
        score = _clip(trade_imb * 0.6 + (book_imb or 0.0) * 0.4)
        reason = f"trade-imbalance={trade_imb:+.2f}, book-imbalance={book_imb:+.2f}"
        return Signal(self.name, score, reason)


DEFAULT_AGENTS = [MomentumAgent(), RSIReversionAgent(), BollingerBreakoutAgent(), OrderFlowAgent()]
