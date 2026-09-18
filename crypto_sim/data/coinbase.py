"""Coinbase Exchange public candles API — no auth key required.

Endpoint: GET /products/{product_id}/candles
Response candles: [time, low, high, open, close, volume] (oldest→newest varies;
we always sort ascending by time).
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

from crypto_sim.config import (
    BACKOFF_BASE_S,
    CACHE_DIR,
    CANDLES_PER_REQUEST,
    COINBASE_BASE_URL,
    GRANULARITIES,
    MAX_RETRIES,
    REQUEST_SLEEP_S,
)


def _cache_path(product_id: str, granularity: int, start: datetime, end: datetime) -> Path:
    root = Path(CACHE_DIR)
    # Prefer project-relative cache under cwd or package parent
    if not root.is_absolute():
        # Resolve relative to project root (parent of crypto_sim)
        pkg = Path(__file__).resolve().parents[2]
        root = pkg / CACHE_DIR
    root.mkdir(parents=True, exist_ok=True)
    s = start.strftime("%Y%m%d%H%M")
    e = end.strftime("%Y%m%d%H%M")
    safe = product_id.replace("/", "-")
    return root / f"{safe}_g{granularity}_{s}_{e}.csv"


def _parse_candles(raw: list) -> pd.DataFrame:
    if not raw:
        return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    df = pd.DataFrame(raw, columns=["time", "low", "high", "open", "close", "volume"])
    df["time"] = pd.to_datetime(df["time"], unit="s", utc=True)
    df = df.set_index("time").sort_index()
    df = df[~df.index.duplicated(keep="last")]
    df = df[["open", "high", "low", "close", "volume"]].astype(float)
    return df


def fetch_candles(
    product_id: str,
    granularity: int,
    start: datetime,
    end: datetime,
    *,
    use_cache: bool = True,
    session: Optional[requests.Session] = None,
) -> pd.DataFrame:
    """Fetch OHLCV for [start, end), paginating; cache to CSV.

    Rate-limits with sleep + exponential backoff on 429/5xx.
    """
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    start = start.astimezone(timezone.utc)
    end = end.astimezone(timezone.utc)

    cache_file = _cache_path(product_id, granularity, start, end)
    if use_cache and cache_file.exists():
        df = pd.read_csv(cache_file, parse_dates=["time"], index_col="time")
        if df.index.tz is None:
            df.index = df.index.tz_localize("UTC")
        else:
            df.index = df.index.tz_convert("UTC")
        df = df.sort_index()
        df = df[~df.index.duplicated(keep="last")]
        return df

    sess = session or requests.Session()
    url = f"{COINBASE_BASE_URL}/products/{product_id}/candles"
    step = timedelta(seconds=granularity * CANDLES_PER_REQUEST)
    chunks: list[pd.DataFrame] = []
    cursor = start

    while cursor < end:
        chunk_end = min(cursor + step, end)
        params = {
            "granularity": granularity,
            "start": cursor.isoformat().replace("+00:00", "Z"),
            "end": chunk_end.isoformat().replace("+00:00", "Z"),
        }
        raw = None
        for attempt in range(MAX_RETRIES):
            try:
                time.sleep(REQUEST_SLEEP_S)
                resp = sess.get(url, params=params, timeout=30)
                if resp.status_code == 429 or resp.status_code >= 500:
                    wait = BACKOFF_BASE_S * (2**attempt)
                    time.sleep(wait)
                    continue
                resp.raise_for_status()
                raw = resp.json()
                break
            except (requests.RequestException, ValueError):
                wait = BACKOFF_BASE_S * (2**attempt)
                time.sleep(wait)
        if raw is None:
            # Skip chunk on persistent failure
            cursor = chunk_end
            continue
        part = _parse_candles(raw)
        if not part.empty:
            chunks.append(part)
        cursor = chunk_end

    if not chunks:
        df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df.index = pd.DatetimeIndex([], tz="UTC", name="time")
    else:
        df = pd.concat(chunks).sort_index()
        df = df[~df.index.duplicated(keep="last")]
        # Keep bars strictly within [start, end)
        df = df.loc[(df.index >= start) & (df.index < end)]

    if use_cache and not df.empty:
        out = df.reset_index()
        out.to_csv(cache_file, index=False)

    return df


def load_ohlcv(
    product_id: str,
    timeframe: str,
    start: datetime,
    end: datetime,
    *,
    use_cache: bool = True,
) -> pd.DataFrame:
    """Convenience: timeframe label → granularity."""
    if timeframe not in GRANULARITIES:
        raise ValueError(f"Unknown timeframe {timeframe}; choose from {list(GRANULARITIES)}")
    return fetch_candles(product_id, GRANULARITIES[timeframe], start, end, use_cache=use_cache)


def window_bounds(end_offset_days: int, length_days: int, now: Optional[datetime] = None):
    """Return (start, end) UTC datetimes for a historical window."""
    now = now or datetime.now(timezone.utc)
    end = now - timedelta(days=end_offset_days)
    start = end - timedelta(days=length_days)
    return start, end
