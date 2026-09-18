"""Backtest con UN SOLO portafoglio condiviso su più crypto: ad ogni istante
il team di agenti valuta tutte le crypto seguite e sceglie da solo, senza
che l'utente debba indicarla, la MIGLIORE opportunità su cui entrare —
esattamente come già fa in tempo reale nel paper trading live."""
from __future__ import annotations

import pandas as pd

from .manager import ManagerAgent
from .portfolio import Portfolio


def align_candles(candles_by_product: dict) -> dict:
    """Tiene solo i timestamp comuni a TUTTE le crypto, così si può avanzare
    nel tempo un istante alla volta confrontando le opportunità fra loro."""
    valid = {p: c for p, c in candles_by_product.items()
             if isinstance(c, pd.DataFrame) and not c.empty}
    if not valid:
        return {}
    common_index = None
    for c in valid.values():
        common_index = c.index if common_index is None else common_index.intersection(c.index)
    if common_index is None or len(common_index) == 0:
        return {}
    return {p: c.loc[common_index].sort_index() for p, c in valid.items()}


def run_multi_asset_backtest(candles_by_product: dict, manager: ManagerAgent, portfolio: Portfolio,
                              warmup: int = 25) -> dict:
    aligned = align_candles(candles_by_product)
    if not aligned:
        raise ValueError("Nessun timestamp in comune tra le crypto selezionate (o dati mancanti).")

    timeline = next(iter(aligned.values())).index
    if len(timeline) <= warmup:
        raise ValueError("Serie storica troppo corta per il warmup degli indicatori")

    choice_log = []

    for i in range(warmup, len(timeline)):
        ts = timeline[i]
        prices = {}
        candidates = []  # (score, product, price, reason)

        for product, candles in aligned.items():
            window = candles.iloc[: i + 1]
            price = float(window["close"].iloc[-1])
            prices[product] = price

            portfolio.check_stop_and_target(product, price, ts)

            has_position = product in portfolio.positions
            decision = manager.decide(window, orderflow=None, has_position=has_position)

            if decision.action == "SELL" and has_position:
                portfolio.sell(product, price, ts, reason=decision.reason)
            elif decision.action == "BUY" and not has_position:
                candidates.append((decision.score, product, price, decision.reason))

        if candidates:
            candidates.sort(key=lambda c: c[0], reverse=True)
            best_score, best_product, best_price, best_reason = candidates[0]
            trade = portfolio.buy(best_product, best_price, ts, reason=best_reason)
            if trade:
                choice_log.append({
                    "timestamp": ts, "scelta": best_product, "score": best_score,
                    "alternative_scartate": [c[1] for c in candidates[1:]],
                })

        portfolio.record_equity(ts, prices)

    last_ts = timeline[-1]
    last_prices = {p: float(c["close"].iloc[-1]) for p, c in aligned.items()}
    for product in list(portfolio.positions.keys()):
        portfolio.sell(product, last_prices[product], last_ts, reason="chiusura fine backtest")
    portfolio.record_equity(last_ts, last_prices)

    metrics = portfolio.metrics(last_prices)
    metrics["choice_log"] = choice_log
    return metrics
