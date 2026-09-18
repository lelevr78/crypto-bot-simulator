"""Manager: weighted combination of agent scores → BUY / SELL / HOLD."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Dict, Mapping

from crypto_sim.config import (
    DEFAULT_BUY_THRESHOLD,
    DEFAULT_SELL_THRESHOLD,
    DEFAULT_WEIGHTS,
)


class Decision(str, Enum):
    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass
class ManagerResult:
    combined_score: float
    decision: Decision
    agent_scores: Dict[str, float]


class Manager:
    def __init__(
        self,
        weights: Mapping[str, float] | None = None,
        buy_threshold: float = DEFAULT_BUY_THRESHOLD,
        sell_threshold: float = DEFAULT_SELL_THRESHOLD,
    ):
        w = dict(weights or DEFAULT_WEIGHTS)
        total = sum(w.values()) or 1.0
        self.weights = {k: v / total for k, v in w.items()}
        self.buy_threshold = buy_threshold
        self.sell_threshold = sell_threshold

    def decide(self, agent_scores: Mapping[str, float]) -> ManagerResult:
        combined = 0.0
        used = 0.0
        for name, weight in self.weights.items():
            if name in agent_scores:
                combined += weight * float(agent_scores[name])
                used += weight
        if used > 0 and abs(used - 1.0) > 1e-9:
            combined /= used
        if combined >= self.buy_threshold:
            decision = Decision.BUY
        elif combined <= self.sell_threshold:
            decision = Decision.SELL
        else:
            decision = Decision.HOLD
        return ManagerResult(
            combined_score=combined,
            decision=decision,
            agent_scores=dict(agent_scores),
        )
