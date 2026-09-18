"""Feed live da Coinbase Advanced Trade WebSocket (pubblico, nessuna API key).

Aggrega i trade in barre OHLCV in tempo reale e tiene traccia dell'order-flow
(volume buy/sell e sbilanciamento del book) per la barra ANCORA IN FORMAZIONE:
è questo che permette al team di agenti di valutare la barra corrente prima
che si chiuda, invece di aspettare la chiusura della candela.
"""
from __future__ import annotations

import json
import threading
import time
from collections import defaultdict, deque
from datetime import datetime, timezone

import numpy as np
import pandas as pd

WS_URL = "wss://advanced-trade-ws.coinbase.com"


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return np.nan


class _ProductState:
    def __init__(self, bar_seconds: int, max_bars: int):
        self.bar_seconds = bar_seconds
        self.bars = deque(maxlen=max_bars)   # barre chiuse: dict open/high/low/close/volume/timestamp
        self.cur_bar = None                  # barra in formazione (dict)
        self.bids: dict[float, float] = {}
        self.asks: dict[float, float] = {}
        self.buy_volume = 0.0
        self.sell_volume = 0.0
        self.last_price = np.nan

    def _bucket_start(self, ts: float) -> float:
        return ts - (ts % self.bar_seconds)

    def on_trade(self, price: float, size: float, side: str, ts: float):
        self.last_price = price
        bucket = self._bucket_start(ts)
        if self.cur_bar is None or self.cur_bar["bucket"] != bucket:
            if self.cur_bar is not None:
                self.bars.append(self.cur_bar)
            self.cur_bar = {"bucket": bucket, "open": price, "high": price,
                             "low": price, "close": price, "volume": 0.0}
            self.buy_volume = 0.0
            self.sell_volume = 0.0
        b = self.cur_bar
        b["high"] = max(b["high"], price)
        b["low"] = min(b["low"], price)
        b["close"] = price
        b["volume"] += size
        if side == "BUY":
            self.buy_volume += size
        elif side == "SELL":
            self.sell_volume += size

    def book_imbalance(self, depth: int = 10) -> float:
        bids = sorted(self.bids.items(), reverse=True)[:depth]
        asks = sorted(self.asks.items())[:depth]
        bd = sum(q for _, q in bids)
        ad = sum(q for _, q in asks)
        return (bd - ad) / (bd + ad) if (bd + ad) else 0.0

    def dataframe_with_partial(self) -> pd.DataFrame:
        rows = list(self.bars)
        if self.cur_bar is not None:
            rows = rows + [self.cur_bar]
        if not rows:
            return pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
        df = pd.DataFrame(rows)
        df.index = pd.to_datetime(df.pop("bucket"), unit="s", utc=True)
        return df[["open", "high", "low", "close", "volume"]]

    def orderflow(self) -> dict:
        return {
            "buy_volume": self.buy_volume,
            "sell_volume": self.sell_volume,
            "book_imbalance": self.book_imbalance(),
        }


class LiveFeed:
    def __init__(self, products: list[str], bar_seconds: int = 15, max_bars: int = 300):
        self.products = products
        self.bar_seconds = bar_seconds
        self._states = {p: _ProductState(bar_seconds, max_bars) for p in products}
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.status = "fermo"
        self.last_error = ""

    # -- lifecycle -----------------------------------------------------
    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def is_running(self) -> bool:
        return bool(self._thread and self._thread.is_alive() and not self._stop.is_set())

    # -- public read API -------------------------------------------------
    def state_for(self, product: str):
        with self._lock:
            st = self._states[product]
            return st.dataframe_with_partial(), st.orderflow(), st.last_price

    def all_last_prices(self) -> dict[str, float]:
        with self._lock:
            return {p: s.last_price for p, s in self._states.items()}

    # -- internals ---------------------------------------------------
    def _process_trades(self, msg):
        for ev in msg.get("events", []):
            for t in ev.get("trades", []):
                p = t.get("product_id")
                if p not in self._states:
                    continue
                price, size = _f(t.get("price")), _f(t.get("size"))
                side = str(t.get("side", "")).upper()
                if not np.isfinite(price) or not np.isfinite(size):
                    continue
                ts = time.time()
                with self._lock:
                    self._states[p].on_trade(price, size, side, ts)

    def _process_l2(self, msg):
        for ev in msg.get("events", []):
            for u in ev.get("updates", []):
                p = u.get("product_id")
                if p not in self._states:
                    continue
                side = str(u.get("side", "")).upper()
                price, qty = _f(u.get("price_level")), _f(u.get("new_quantity"))
                if not np.isfinite(price) or not np.isfinite(qty):
                    continue
                with self._lock:
                    book = self._states[p].bids if side == "BID" else self._states[p].asks
                    if qty <= 0:
                        book.pop(price, None)
                    else:
                        book[price] = qty

    def _run(self):
        try:
            import websocket
        except ImportError:
            self.last_error = "Modulo 'websocket-client' non installato."
            self.status = "errore"
            return

        while not self._stop.is_set():
            ws = None
            try:
                ws = websocket.create_connection(WS_URL, timeout=10)
                ws.send(json.dumps({"type": "subscribe", "channel": "market_trades",
                                     "product_ids": self.products}))
                ws.send(json.dumps({"type": "subscribe", "channel": "level2",
                                     "product_ids": self.products}))
                self.status = "connesso"
                ws.settimeout(2)
                while not self._stop.is_set():
                    try:
                        msg = json.loads(ws.recv())
                    except Exception as e:
                        if "timed out" in str(e).lower():
                            continue
                        raise
                    ch = msg.get("channel")
                    if ch == "market_trades":
                        self._process_trades(msg)
                    elif ch == "l2_data":
                        self._process_l2(msg)
            except Exception as e:
                self.last_error = f"{type(e).__name__}: {e}"
                self.status = "riconnessione..."
                time.sleep(3)
            finally:
                try:
                    if ws:
                        ws.close()
                except Exception:
                    pass
        self.status = "fermo"
