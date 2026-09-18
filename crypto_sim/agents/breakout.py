"""Breakout agent: price vs Bollinger Bands."""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_sim.agents.base import BaseAgent
from crypto_sim.config import BB_PERIOD, BB_STD
from crypto_sim.indicators import bollinger, clip_score


class BreakoutAgent(BaseAgent):
    name = "breakout"

    def __init__(self, period: int = BB_PERIOD, num_std: float = BB_STD):
        self.period = period
        self.num_std = num_std

    def prepare(self, df: pd.DataFrame) -> pd.Series:
        close = df["close"]
        lower, mid, upper = bollinger(close, self.period, self.num_std)
        half = (upper - lower) / 2.0
        band_pos = (close - mid) / (half + 1e-12)
        raw = np.tanh(band_pos.fillna(0.0))
        out = pd.Series(clip_score(raw), index=df.index, name=self.name)
        out.iloc[: self.period] = 0.0
        return out
