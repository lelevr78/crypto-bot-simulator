"""Backtest aggregato su più crypto per misurare il win rate del team di
agenti in modo statisticamente più solido di un singolo test su un asset
e un periodo soli (che può ingannare per pura fortuna/overfitting)."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

import pandas as pd

from .backtester import run_backtest
from .data import fetch_candles
from .manager import ManagerAgent
from .portfolio import Portfolio


def fetch_multi_candles(products: list[str], granularity: int, hours: int) -> dict:
    """Scarica le candele una sola volta per prodotto (in parallelo, così periodi
    lunghi o molte crypto non richiedono di aspettare un prodotto alla volta), da
    riusare in più backtest senza rifare le stesse richieste di rete. Il limite di
    frequenza verso l'API di Coinbase resta rispettato perché è condiviso tra thread
    (vedi crypto_bot/data.py)."""
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    def _fetch(product):
        try:
            return product, fetch_candles(product, granularity, start, end)
        except Exception as e:
            return product, e

    out = {}
    with ThreadPoolExecutor(max_workers=min(4, max(1, len(products)))) as executor:
        for product, result in executor.map(_fetch, products):
            out[product] = result
    return out


def run_batch_from_candles(candles_by_product: dict, manager_kwargs: dict | None = None,
                            portfolio_kwargs: dict | None = None, warmup: int = 25):
    manager_kwargs = manager_kwargs or {}
    portfolio_kwargs = portfolio_kwargs or {}

    rows = []
    all_trades = []
    for product, candles in candles_by_product.items():
        if isinstance(candles, Exception):
            rows.append({"product": product, "error": f"{type(candles).__name__}: {candles}"})
            continue
        if candles is None or len(candles) <= warmup:
            rows.append({"product": product, "error": "dati storici insufficienti"})
            continue

        manager = ManagerAgent(**manager_kwargs)
        portfolio = Portfolio(**portfolio_kwargs)
        metrics = run_backtest(candles, manager, portfolio, product, warmup=warmup)
        buy_hold_pct = (candles["close"].iloc[-1] / candles["close"].iloc[0] - 1) * 100
        rows.append({"product": product, **metrics, "buy_hold_pct": buy_hold_pct})

        for t in portfolio.trade_log:
            row = dict(t)
            row["product"] = product
            all_trades.append(row)

    results = pd.DataFrame(rows)
    trades_df = pd.DataFrame(all_trades)
    closed = trades_df[trades_df["side"] == "SELL"] if not trades_df.empty else trades_df

    summary = {
        "num_products_tested": len(candles_by_product),
        "num_products_with_data": int((~results.get("error", pd.Series(dtype=object)).notna()).sum())
        if "error" in results else len(candles_by_product),
        "total_closed_trades": int(len(closed)),
        "overall_win_rate_pct": float((closed["pnl"] > 0).mean() * 100) if len(closed) else float("nan"),
        "avg_return_pct": float(results["total_return_pct"].mean()) if "total_return_pct" in results else float("nan"),
        "avg_buy_hold_pct": float(results["buy_hold_pct"].mean()) if "buy_hold_pct" in results else float("nan"),
        "avg_max_drawdown_pct": float(results["max_drawdown_pct"].mean()) if "max_drawdown_pct" in results else float("nan"),
    }
    return results, trades_df, summary


def run_batch(products: list[str], granularity: int, hours: int,
              manager_kwargs: dict | None = None, portfolio_kwargs: dict | None = None,
              warmup: int = 25):
    candles_by_product = fetch_multi_candles(products, granularity, hours)
    return run_batch_from_candles(candles_by_product, manager_kwargs, portfolio_kwargs, warmup)


def run_threshold_sweep(candles_by_product: dict, thresholds: list[float],
                         weights: dict | None = None, portfolio_kwargs: dict | None = None,
                         warmup: int = 25) -> pd.DataFrame:
    """Confronta più soglie BUY/SELL simmetriche sugli STESSI dati storici (già scaricati
    una volta sola), per trovare il punto di equilibrio tra 'troppo prudente' (0 trade,
    nessuna opportunità colta) e 'troppo aggressiva' (overtrading sul rumore, win rate
    basso, drawdown alto per via delle commissioni e degli stop-loss ravvicinati)."""
    rows = []
    for th in thresholds:
        manager_kwargs = {"weights": weights, "buy_threshold": th, "sell_threshold": -th}
        _, _, summary = run_batch_from_candles(candles_by_product, manager_kwargs, portfolio_kwargs, warmup)
        rows.append({
            "soglia": th,
            "trade_chiusi": summary["total_closed_trades"],
            "win_rate_pct": summary["overall_win_rate_pct"],
            "return_medio_pct": summary["avg_return_pct"],
            "drawdown_medio_pct": summary["avg_max_drawdown_pct"],
        })
    return pd.DataFrame(rows)
