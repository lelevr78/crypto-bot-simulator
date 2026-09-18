"""Momentum agent: fast/slow EMA cross + ROC."""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_sim.agents.base import BaseAgent
from crypto_sim.config import MOMENTUM_FAST, MOMENTUM_ROC_PERIOD, MOMENTUM_SLOW
from crypto_sim.indicators import clip_score, ema, roc


class MomentumAgent(BaseAgent):
    name = "momentum"

    def __init__(
        self,
        fast: int = MOMENTUM_FAST,
        slow: int = MOMENTUM_SLOW,
        roc_period: int = MOMENTUM_ROC_PERIOD,
    ):
        self.fast = fast
        self.slow = slow
        self.roc_period = roc_period

    def prepare(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        fast_ema = ema(close, self.fast)
        slow_ema = ema(close, self.slow)
        r = roc(close, self.roc_period).fillna(0.0)
        spread = (fast_ema - slow_ema) / (slow_ema + 1e-12)
        raw = np.tanh(spread * 50.0) * 0.6 + np.tanh(r * 20.0) * 0.4
        out = pd.Series(clip_score(raw), index=df.index, name=self.name)
        warmup = self.slow + self.roc_period
        out.iloc[:warmup] = 0.0
        return out
