"""Order-flow PROXY from OHLCV only (no L2 book / trades tape).

Body/wick/volume imbalance as a stand-in for buying vs selling pressure.
Documented as a proxy — not true order-flow microstructure.
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from crypto_sim.agents.base import BaseAgent
from crypto_sim.indicators import clip_score


class OrderFlowAgent(BaseAgent):
    """OHLCV proxy for order-flow imbalance.

    Components (causal, last bar + short lookback):
    - Body direction & size relative to range
    - Upper/lower wick asymmetry
    - Volume vs recent average (signed by body)
    """

    name = "order_flow"

    def __init__(self, vol_lookback: int = 20):
        self.vol_lookback = vol_lookback

    def prepare(self, df: pd.DataFrame) -> pd.Series:
        o = df["open"].to_numpy(dtype=float)
        h = df["high"].to_numpy(dtype=float)
        l = df["low"].to_numpy(dtype=float)
        c = df["close"].to_numpy(dtype=float)
        v = df["volume"].to_numpy(dtype=float)
        rng = h - l
        rng_safe = np.where(rng > 0, rng, np.nan)
        body = c - o
        body_frac = body / rng_safe
        upper_wick = h - np.maximum(o, c)
        lower_wick = np.minimum(o, c) - l
        wick_imb = (lower_wick - upper_wick) / rng_safe
        vol_mean = (
            pd.Series(v).rolling(self.vol_lookback, min_periods=1).mean().shift(1).to_numpy()
        )
        vol_ratio = v / (vol_mean + 1e-12)
        vol_sign = np.sign(body)
        vol_comp = np.tanh(vol_ratio - 1.0) * vol_sign
        raw = 0.45 * np.nan_to_num(body_frac, nan=0.0) + 0.25 * np.nan_to_num(
            wick_imb, nan=0.0
        ) + 0.30 * np.nan_to_num(vol_comp, nan=0.0)
        out = pd.Series(clip_score(raw), index=df.index, name=self.name)
        out.iloc[0] = 0.0
        return out
