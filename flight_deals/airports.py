"""Anagrafica aeroporti usata dal radar (codice IATA, città, paese, coordinate)."""

from __future__ import annotations

import math
from dataclasses import dataclass


@dataclass(frozen=True)
class Airport:
    code: str
    city: str
    country: str
    lat: float
    lon: float


ORIGINS = [
    Airport("VRN", "Verona", "Italia", 45.396, 10.888),
    Airport("VCE", "Venezia", "Italia", 45.505, 12.352),
    Airport("BGY", "Bergamo", "Italia", 45.674, 9.704),
    Airport("MXP", "Milano Malpensa", "Italia", 45.630, 8.723),
    Airport("BLQ", "Bologna", "Italia", 44.535, 11.289),
]

DESTINATIONS = [
    Airport("BCN", "Barcellona", "Spagna", 41.297, 2.078),
    Airport("MAD", "Madrid", "Spagna", 40.472, -3.561),
    Airport("PMI", "Palma di Maiorca", "Spagna", 39.552, 2.739),
    Airport("LIS", "Lisbona", "Portogallo", 38.774, -9.134),
    Airport("OPO", "Porto", "Portogallo", 41.248, -8.681),
    Airport("CDG", "Parigi", "Francia", 49.010, 2.548),
    Airport("LGW", "Londra", "Regno Unito", 51.148, -0.190),
    Airport("DUB", "Dublino", "Irlanda", 53.421, -6.270),
    Airport("AMS", "Amsterdam", "Paesi Bassi", 52.310, 4.768),
    Airport("BER", "Berlino", "Germania", 52.362, 13.501),
    Airport("PRG", "Praga", "Rep. Ceca", 50.101, 14.260),
    Airport("VIE", "Vienna", "Austria", 48.110, 16.570),
    Airport("BUD", "Budapest", "Ungheria", 47.437, 19.256),
    Airport("CPH", "Copenaghen", "Danimarca", 55.618, 12.656),
    Airport("ARN", "Stoccolma", "Svezia", 59.652, 17.919),
    Airport("ATH", "Atene", "Grecia", 37.936, 23.947),
    Airport("JTR", "Santorini", "Grecia", 36.399, 25.479),
    Airport("CTA", "Catania", "Italia", 37.467, 15.066),
    Airport("PMO", "Palermo", "Italia", 38.176, 13.091),
    Airport("CAG", "Cagliari", "Italia", 39.251, 9.054),
    Airport("MLA", "Malta", "Malta", 35.857, 14.477),
    Airport("IST", "Istanbul", "Turchia", 41.275, 28.752),
    Airport("RAK", "Marrakech", "Marocco", 31.607, -8.036),
    Airport("TFS", "Tenerife", "Spagna", 28.044, -16.573),
    Airport("KEF", "Reykjavík", "Islanda", 63.985, -22.606),
    Airport("DXB", "Dubai", "Emirati Arabi", 25.253, 55.364),
    Airport("JFK", "New York", "Stati Uniti", 40.641, -73.778),
    Airport("MIA", "Miami", "Stati Uniti", 25.795, -80.287),
    Airport("LAX", "Los Angeles", "Stati Uniti", 33.942, -118.408),
    Airport("YYZ", "Toronto", "Canada", 43.677, -79.625),
    Airport("CUN", "Cancún", "Messico", 21.037, -86.877),
    Airport("GRU", "San Paolo", "Brasile", -23.435, -46.473),
    Airport("BKK", "Bangkok", "Thailandia", 13.690, 100.750),
    Airport("NRT", "Tokyo", "Giappone", 35.772, 140.393),
    Airport("SIN", "Singapore", "Singapore", 1.364, 103.991),
    Airport("MLE", "Malé (Maldive)", "Maldive", 4.192, 73.529),
    Airport("CPT", "Città del Capo", "Sudafrica", -33.965, 18.602),
    Airport("SYD", "Sydney", "Australia", -33.940, 151.175),
]

BY_CODE = {a.code: a for a in ORIGINS + DESTINATIONS}


def distance_km(a: Airport, b: Airport) -> float:
    """Distanza ortodromica (haversine) in km."""
    r = 6371.0
    p1, p2 = math.radians(a.lat), math.radians(b.lat)
    dp, dl = p2 - p1, math.radians(b.lon - a.lon)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))
