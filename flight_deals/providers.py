"""Sorgenti tariffe.

- ``SimulatedProvider``: genera tariffe realistiche (distanza, stagionalità,
  anticipo di prenotazione, rumore) con rari ribassi anomali/error fare.
  Funziona offline ed è il default.
- ``TravelpayoutsProvider``: tariffe reali dalla Data API di Travelpayouts
  (Aviasales). Richiede la variabile d'ambiente ``TRAVELPAYOUTS_TOKEN``.
"""

from __future__ import annotations

import json
import math
import os
import random
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Iterable

from .airports import BY_CODE, DESTINATIONS, ORIGINS, Airport, distance_km


@dataclass(frozen=True)
class Fare:
    origin: str
    destination: str
    depart: date
    ret: date | None
    price: float
    airline: str
    stops: int
    currency: str = "EUR"

    @property
    def route(self) -> tuple[str, str]:
        return (self.origin, self.destination)


SHORT_HAUL_AIRLINES = ["Ryanair", "easyJet", "Wizz Air", "Volotea", "Vueling", "ITA Airways", "Lufthansa"]
LONG_HAUL_AIRLINES = ["ITA Airways", "Emirates", "Qatar Airways", "Lufthansa", "Air France", "KLM", "Turkish Airlines"]


def base_round_trip_price(origin: Airport, dest: Airport) -> float:
    """Prezzo 'normale' A/R in EUR stimato dalla distanza."""
    km = distance_km(origin, dest)
    if km < 1500:
        return 45 + 0.10 * km
    if km < 4000:
        return 90 + 0.085 * km
    return 250 + 0.055 * km


def season_factor(d: date) -> float:
    if d.month in (7, 8):
        return 1.30
    if (d.month == 12 and d.day >= 18) or (d.month == 1 and d.day <= 6):
        return 1.35
    if d.month in (6, 9):
        return 1.10
    if d.month in (1, 2, 11):
        return 0.85
    return 1.0


def advance_factor(days_ahead: int) -> float:
    if days_ahead < 7:
        return 1.70
    if days_ahead < 14:
        return 1.35
    if days_ahead < 30:
        return 1.10
    return 1.0


class SimulatedProvider:
    """Genera combinazioni casuali (origine × destinazione × date × durata)."""

    name = "simulato"

    def __init__(
        self,
        origins: Iterable[str] | None = None,
        seed: int | None = None,
        anomaly_rate: float = 2e-5,
        horizon_days: int = 240,
        today: date | None = None,
    ) -> None:
        codes = list(origins) if origins else [a.code for a in ORIGINS]
        self.origins = [BY_CODE[c] for c in codes]
        self.destinations = DESTINATIONS
        self.rng = random.Random(seed)
        self.anomaly_rate = anomaly_rate
        self.horizon_days = horizon_days
        self._today = today

    @property
    def today(self) -> date:
        return self._today or date.today()

    def routes(self) -> list[tuple[str, str]]:
        return [(o.code, d.code) for o in self.origins for d in self.destinations]

    def sample(self, n: int) -> list[Fare]:
        return [self._one() for _ in range(n)]

    def _one(self) -> Fare:
        rng = self.rng
        o = rng.choice(self.origins)
        d = rng.choice(self.destinations)
        days_ahead = rng.randint(3, self.horizon_days)
        depart = self.today + timedelta(days=days_ahead)
        long_haul = distance_km(o, d) >= 4000
        stay = rng.randint(6, 16) if long_haul else rng.randint(2, 9)
        ret = depart + timedelta(days=stay)

        price = base_round_trip_price(o, d)
        price *= season_factor(depart) * advance_factor(days_ahead)
        if depart.weekday() in (4, 6):  # venerdì / domenica
            price *= 1.08
        stops = 0 if not long_haul else rng.choice([0, 1, 1, 2])
        price *= 1.0 - 0.07 * stops
        price *= math.exp(rng.gauss(0, 0.13))

        if rng.random() < self.anomaly_rate:
            # Error fare / flash sale: dal 45% al 92% in meno.
            price *= rng.uniform(0.08, 0.55)

        airlines = LONG_HAUL_AIRLINES if long_haul else SHORT_HAUL_AIRLINES
        return Fare(o.code, d.code, depart, ret, round(max(price, 9.0), 2), rng.choice(airlines), stops)


class TravelpayoutsProvider:
    """Tariffe reali (cache Aviasales) via Travelpayouts Data API v3.

    Scorre le rotte a rotazione: a ogni chiamata interroga un mese di partenza
    per una rotta e restituisce tutte le combinazioni di date trovate.
    """

    name = "travelpayouts"
    URL = "https://api.travelpayouts.com/aviasales/v3/prices_for_dates"

    def __init__(self, token: str | None = None, origins: Iterable[str] | None = None, months_ahead: int = 6) -> None:
        self.token = token or os.environ.get("TRAVELPAYOUTS_TOKEN", "")
        if not self.token:
            raise ValueError("TRAVELPAYOUTS_TOKEN mancante")
        codes = list(origins) if origins else [a.code for a in ORIGINS]
        self._routes = [(o, d.code) for o in codes for d in DESTINATIONS]
        self.months_ahead = months_ahead
        self._cursor = 0

    def routes(self) -> list[tuple[str, str]]:
        return list(self._routes)

    def sample(self, n: int) -> list[Fare]:
        # n = combinazioni desiderate; ogni chiamata API ne restituisce fino a 100.
        fares: list[Fare] = []
        calls = max(1, n // 100)
        for _ in range(calls):
            origin, dest = self._routes[self._cursor % len(self._routes)]
            month_offset = (self._cursor // len(self._routes)) % self.months_ahead
            self._cursor += 1
            first = date.today().replace(day=1)
            month = (first + timedelta(days=32 * month_offset)).strftime("%Y-%m")
            fares.extend(self._fetch(origin, dest, month))
        return fares

    def _fetch(self, origin: str, dest: str, month: str) -> list[Fare]:
        query = urllib.parse.urlencode({
            "origin": origin, "destination": dest, "departure_at": month,
            "one_way": "false", "currency": "eur", "sorting": "price",
            "limit": 100, "token": self.token,
        })
        try:
            with urllib.request.urlopen(f"{self.URL}?{query}", timeout=20) as resp:
                payload = json.load(resp)
        except (OSError, ValueError):
            return []
        out = []
        for row in payload.get("data") or []:
            try:
                ret = row.get("return_at")
                out.append(Fare(
                    origin=row["origin"], destination=row["destination"],
                    depart=date.fromisoformat(row["departure_at"][:10]),
                    ret=date.fromisoformat(ret[:10]) if ret else None,
                    price=float(row["price"]), airline=row.get("airline", ""),
                    stops=int(row.get("transfers", 0)),
                ))
            except (KeyError, TypeError, ValueError):
                continue
        return out
