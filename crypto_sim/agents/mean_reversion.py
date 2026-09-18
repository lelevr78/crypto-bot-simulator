"""Mean-reversion agent: RSI contrarian."""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_sim.agents.base import BaseAgent
from crypto_sim.config import RSI_OVERBOUGHT, RSI_OVERSOLD, RSI_PERIOD
from crypto_sim.indicators import clip_score, rsi


class MeanReversionAgent(BaseAgent):
    name = "mean_reversion"

    def __init__(
        self,
        period: int = RSI_PERIOD,
        oversold: float = RSI_OVERSOLD,
        overbought: float = RSI_OVERBOUGHT,
    ):
        self.period = period
        self.oversold = oversold
        self.overbought = overbought

    def prepare(self, df: pd.DataFrame) -> pd.Series:
        r = rsi(df["close"], self.period)
        val = r.to_numpy(dtype=float)
        raw = np.zeros_like(val)
        # Contrarian mapping
        oversold_mask = val <= self.oversold
        overbought_mask = val >= self.overbought
        mid = ~(oversold_mask | overbought_mask)
        raw[oversold_mask] = (self.oversold - val[oversold_mask]) / max(self.oversold, 1e-9)
        raw[overbought_mask] = -(val[overbought_mask] - self.overbought) / max(
            100.0 - self.overbought, 1e-9
        )
        raw[mid] = (50.0 - val[mid]) / 50.0 * 0.3
        out = pd.Series(clip_score(raw), index=df.index, name=self.name)
        out.iloc[: self.period + 1] = 0.0
        return out
