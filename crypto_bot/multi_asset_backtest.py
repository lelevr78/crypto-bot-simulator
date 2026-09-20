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

            if decision.action == "SELL" and has_position and portfolio.held_long_enough(product, ts):
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


def run_threshold_sweep(candles_by_product: dict, thresholds: list[float],
                         weights: dict | None = None, portfolio_kwargs: dict | None = None,
                         warmup: int = 25) -> pd.DataFrame:
    """Come il confronto soglie della Validazione multi-crypto, ma per il portafoglio
    condiviso: qui il numero di trade è molto più sensibile alla soglia, perché ogni
    istante confronta TUTTE le crypto insieme e basta che una sola superi la soglia
    per scattare un trade — quindi serve una soglia più alta che nel test su un asset solo."""
    rows = []
    for th in thresholds:
        manager = ManagerAgent(weights=weights, buy_threshold=th, sell_threshold=-th)
        portfolio = Portfolio(**(portfolio_kwargs or {}))
        try:
            metrics = run_multi_asset_backtest(candles_by_product, manager, portfolio, warmup=warmup)
            has_trades = metrics["num_trades"] > 0
            rows.append({
                "soglia": th,
                "trade_chiusi": metrics["num_trades"],
                "win_rate_pct": metrics["win_rate_pct"] if has_trades else float("nan"),
                "return_pct": metrics["total_return_pct"] if has_trades else float("nan"),
                "drawdown_pct": metrics["max_drawdown_pct"],
            })
        except ValueError:
            rows.append({"soglia": th, "trade_chiusi": 0, "win_rate_pct": float("nan"),
                         "return_pct": float("nan"), "drawdown_pct": float("nan")})
    return pd.DataFrame(rows)
