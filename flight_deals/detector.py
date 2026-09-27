"""Rilevamento offerte anomale.

Per ogni rotta si mantiene lo storico recente dei prezzi osservati. Il
"prezzo normale" è la mediana; la dispersione è misurata con la MAD
(robusta agli outlier). Una tariffa è un'offerta quando:

  1. lo storico ha almeno ``min_samples`` osservazioni;
  2. lo sconto rispetto alla mediana è >= ``min_discount`` (default 50%);
  3. lo z-score robusto è >= ``min_z`` (default 2.5: il ribasso è davvero insolito,
     non semplice rumore di una rotta molto volatile).

Le tariffe anomale non entrano nello storico, così un'ondata di error fare
non abbassa il prezzo normale di riferimento.
"""

from __future__ import annotations

import statistics
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timezone

from .providers import Fare

LEVELS = [(0.75, "Error fare"), (0.60, "Super offerta"), (0.0, "Ottimo prezzo")]


def level_for(discount: float) -> str:
    return next(label for threshold, label in LEVELS if discount >= threshold)


@dataclass
class Deal:
    fare: Fare
    normal_price: float
    discount: float
    zscore: float
    min_seen: float
    samples: int
    found_at: datetime

    @property
    def level(self) -> str:
        return level_for(self.discount)


class RouteStats:
    def __init__(self, maxlen: int, refresh_every: int) -> None:
        self.prices: deque[float] = deque(maxlen=maxlen)
        self.refresh_every = refresh_every
        self._since_refresh = 0
        self.median = 0.0
        self.mad = 0.0
        self.min_seen = float("inf")

    def add(self, price: float) -> None:
        self.prices.append(price)
        self.min_seen = min(self.min_seen, price)
        self._since_refresh += 1
        if self._since_refresh >= self.refresh_every or len(self.prices) <= self.refresh_every:
            self.refresh()

    def refresh(self) -> None:
        self._since_refresh = 0
        self.median = statistics.median(self.prices)
        self.mad = statistics.median(abs(p - self.median) for p in self.prices)


class DealDetector:
    def __init__(
        self,
        min_samples: int = 30,
        min_discount: float = 0.50,
        min_z: float = 2.5,
        history: int = 400,
        refresh_every: int = 20,
    ) -> None:
        self.min_samples = min_samples
        self.min_discount = min_discount
        self.min_z = min_z
        self.history = history
        self.refresh_every = refresh_every
        self.routes: dict[tuple[str, str], RouteStats] = {}

    def stats(self, route: tuple[str, str]) -> RouteStats:
        st = self.routes.get(route)
        if st is None:
            st = self.routes[route] = RouteStats(self.history, self.refresh_every)
        return st

    def observe(self, fare: Fare, now: datetime | None = None) -> Deal | None:
        st = self.stats(fare.route)
        if len(st.prices) >= self.min_samples and st.median > 0:
            discount = 1 - fare.price / st.median
            # 1.4826 * MAD ≈ deviazione standard per dati normali.
            sigma = max(1.4826 * st.mad, 0.02 * st.median)
            z = (st.median - fare.price) / sigma
            if discount >= self.min_discount and z >= self.min_z:
                return Deal(
                    fare=fare,
                    normal_price=round(st.median, 2),
                    discount=round(discount, 4),
                    zscore=round(z, 2),
                    min_seen=round(st.min_seen, 2),
                    samples=len(st.prices),
                    found_at=now or datetime.now(timezone.utc),
                )
        st.add(fare.price)
        return None

    def ready_routes(self) -> int:
        return sum(1 for s in self.routes.values() if len(s.prices) >= self.min_samples)
