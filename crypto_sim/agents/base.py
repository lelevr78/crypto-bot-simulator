"""Base agent interface."""

from __future__ import annotations

from abc import ABC, abstractmethod

import pandas as pd


class BaseAgent(ABC):
    name: str = "base"

    @abstractmethod
    def prepare(self, df: pd.DataFrame) -> pd.Series:
        """Vectorized causal scores for every bar (uses only past+current via rolling/ewm)."""

    def score(self, df: pd.DataFrame, idx: int) -> float:
        """Score at bar idx using only data ≤ idx (via prepare slice)."""
        sub = df.iloc[: idx + 1]
        s = self.prepare(sub)
        return float(s.iloc[-1]) if len(s) else 0.0
