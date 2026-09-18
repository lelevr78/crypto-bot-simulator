"""Central configuration for the paper-trading crypto simulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Coinbase public API
COINBASE_BASE_URL = "https://api.exchange.coinbase.com"
PRODUCTS: List[str] = [
    "BTC-USD",
    "ETH-USD",
    "SOL-USD",
    "XRP-USD",
    "ADA-USD",
    "LINK-USD",
]

# Granularity seconds → label
GRANULARITIES: Dict[str, int] = {
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
}

DEFAULT_TIMEFRAME = "1h"
CACHE_DIR = "data/cache"
RESULTS_DIR = "results"

# Portfolio defaults
DEFAULT_CASH = 10_000.0
DEFAULT_FEE_RATE = 0.003  # 0.3% per side
DEFAULT_POSITION_FRACTION = 1.0  # use full cash on BUY
DEFAULT_STOP_LOSS_PCT = 0.03  # 3%
DEFAULT_TAKE_PROFIT_PCT = 0.06  # 6%

# Manager defaults
DEFAULT_WEIGHTS: Dict[str, float] = {
    "momentum": 0.30,
    "mean_reversion": 0.25,
    "breakout": 0.25,
    "order_flow": 0.20,
}
DEFAULT_BUY_THRESHOLD = 0.25
DEFAULT_SELL_THRESHOLD = -0.25

# Agent indicator params
MOMENTUM_FAST = 12
MOMENTUM_SLOW = 26
MOMENTUM_ROC_PERIOD = 10

RSI_PERIOD = 14
RSI_OVERSOLD = 30.0
RSI_OVERBOUGHT = 70.0

BB_PERIOD = 20
BB_STD = 2.0

# Backtest windows on 1h (~120 days each, distinct historical ranges)
# (label, end_offset_days, length_days)
BACKTEST_WINDOWS: List[Tuple[str, int, int]] = [
    ("W1_older", 200, 120),   # [now-320d, now-200d)
    ("W2_recent", 20, 120),   # [now-140d, now-20d)
]

QUICK_WINDOWS: List[Tuple[str, int, int]] = [
    ("Q1", 90, 45),
    ("Q2", 30, 45),
]

QUICK_PRODUCTS: List[str] = ["BTC-USD", "ETH-USD", "SOL-USD"]

# Rate limiting
REQUEST_SLEEP_S = 0.35
MAX_RETRIES = 5
BACKOFF_BASE_S = 1.0
CANDLES_PER_REQUEST = 300  # Coinbase max

# Walk-forward combined window (days)
WALK_FORWARD_END_OFFSET = 30
WALK_FORWARD_LENGTH = 180  # split 50/50 IS/OOS
