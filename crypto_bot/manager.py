"""ManagerAgent: combina i voti del team di agenti in una decisione unica."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

import numpy as np
import pandas as pd

from .agents import DEFAULT_AGENTS, Signal
from . import indicators as ind


@dataclass
class Decision:
    action: str          # "BUY" | "SELL" | "HOLD"
    score: float
    confidence: float    # 0..1
    signals: list = field(default_factory=list)
    reason: str = ""


DEFAULT_WEIGHTS = {
    "Momentum": 1.0,
    "MeanReversion": 0.7,
    "Breakout": 0.8,
    "OrderFlow": 1.2,   # peso più alto: è il segnale "anticipatorio"
}

# Profili di pesi candidati per la taratura automatica (walk-forward). OrderFlow
# non compare: nel backtest storico non ha mai dati live, quindi è sempre escluso
# dal voto (Signal.available=False) e il suo peso non farebbe differenza — resta
# quello impostato manualmente, usato solo in tempo reale.
WEIGHT_PROFILES = {
    "Equilibrato": {"Momentum": 1.0, "MeanReversion": 1.0, "Breakout": 1.0},
    "Trend forte": {"Momentum": 1.6, "MeanReversion": 0.4, "Breakout": 1.0},
    "Mean-reversion forte": {"Momentum": 0.4, "MeanReversion": 1.6, "Breakout": 1.0},
    "Breakout forte": {"Momentum": 0.8, "MeanReversion": 0.4, "Breakout": 1.8},
}


class ManagerAgent:
    def __init__(self, agents=None, weights=None, buy_threshold=0.35, sell_threshold=-0.35,
                 max_volatility_pct=None):
        self.agents = agents if agents is not None else DEFAULT_AGENTS
        self.weights = weights or DEFAULT_WEIGHTS
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold
        self.max_volatility_pct = max_volatility_pct  # se impostato, congela nuovi BUY in mercati troppo volatili

    def decide(self, df: pd.DataFrame, orderflow: Optional[dict] = None, has_position: bool = False) -> Decision:
        signals = [a.signal(df, orderflow) for a in self.agents]
        active = [s for s in signals if s.available]
        weighted_sum = sum(self.weights.get(s.agent, 1.0) * s.score for s in active)
        weight_total = sum(self.weights.get(s.agent, 1.0) for s in active) or 1.0
        combined = weighted_sum / weight_total if active else 0.0
        agreement = 1.0 - float(np.std([s.score for s in active])) if active else 0.0
        confidence = max(0.0, min(1.0, (abs(combined) * 0.7 + max(0.0, agreement) * 0.3)))

        vol_guard_reason = ""
        volatility_ok = True
        if self.max_volatility_pct is not None and len(df) >= 15:
            atr_pct = (ind.atr(df["high"], df["low"], df["close"]).iloc[-1] / df["close"].iloc[-1]) * 100
            if np.isfinite(atr_pct) and atr_pct > self.max_volatility_pct:
                volatility_ok = False
                vol_guard_reason = f" | volatilità {atr_pct:.2f}% > limite {self.max_volatility_pct:.2f}%, BUY bloccato"

        if combined >= self.buy_threshold and not has_position and volatility_ok:
            action = "BUY"
        elif combined <= self.sell_threshold and has_position:
            action = "SELL"
        elif not volatility_ok and combined >= self.buy_threshold:
            action = "HOLD"
        else:
            action = "HOLD"

        top = sorted(signals, key=lambda s: abs(s.score), reverse=True)
        reason = "; ".join(f"{s.agent}: {s.reason}" for s in top) + vol_guard_reason
        return Decision(action=action, score=combined, confidence=confidence, signals=signals, reason=reason)
