"""Dati storici da Coinbase Exchange (API pubblica REST, nessuna API key richiesta).

Endpoint: GET /products/{product_id}/candles
Documentazione pubblica: https://docs.cdp.coinbase.com/exchange/reference/exchangerestapi_getproductcandles
"""
from __future__ import annotations

import threading
import time
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

BASE_URL = "https://api.exchange.coinbase.com"
VALID_GRANULARITIES = [60, 300, 900, 3600, 21600, 86400]
MAX_CANDLES_PER_CALL = 300

# Limitatore di frequenza GLOBALE (condiviso tra thread): permette di scaricare
# più crypto in parallelo senza superare il rate limit pubblico (~3 richieste/s)
# indipendentemente da quanti thread lo chiamano contemporaneamente.
_rate_lock = threading.Lock()
_last_request_at = [0.0]
_MIN_INTERVAL = 0.34


def _throttle():
    with _rate_lock:
        now = time.monotonic()
        wait = _last_request_at[0] + _MIN_INTERVAL - now
        if wait > 0:
            time.sleep(wait)
        _last_request_at[0] = time.monotonic()


def fetch_candles(product_id: str, granularity: int, start: datetime, end: datetime,
                   timeout: float = 10.0) -> pd.DataFrame:
    """Scarica candele OHLCV storiche, gestendo la paginazione (max 300 candele/call)."""
    if granularity not in VALID_GRANULARITIES:
        raise ValueError(f"granularity deve essere una di {VALID_GRANULARITIES}")

    chunks = []
    window = timedelta(seconds=granularity * MAX_CANDLES_PER_CALL)
    cur_start = start
    session = requests.Session()
    headers = {"User-Agent": "crypto-bot-simulator/1.0"}

    while cur_start < end:
        cur_end = min(cur_start + window, end)
        params = {
            "start": cur_start.isoformat(),
            "end": cur_end.isoformat(),
            "granularity": granularity,
        }
        _throttle()
        resp = session.get(f"{BASE_URL}/products/{product_id}/candles",
                            params=params, headers=headers, timeout=timeout)
        if resp.status_code == 429:
            time.sleep(1.0)
            continue
        resp.raise_for_status()
        data = resp.json()
        if data:
            chunks.extend(data)
        cur_start = cur_end

    if not chunks:
        return pd.DataFrame(columns=["time", "low", "high", "open", "close", "volume"])

    df = pd.DataFrame(chunks, columns=["time", "low", "high", "open", "close", "volume"])
    df = df.drop_duplicates(subset="time").sort_values("time")
    df["timestamp"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("timestamp").drop(columns=["time"])
    return df.astype(float)


def fetch_recent_candles(product_id: str, granularity: int = 300, hours: int = 24) -> pd.DataFrame:
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)
    return fetch_candles(product_id, granularity, start, end)
