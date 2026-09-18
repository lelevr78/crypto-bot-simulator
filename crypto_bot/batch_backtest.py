"""Backtest aggregato su più crypto per misurare il win rate del team di
agenti in modo statisticamente più solido di un singolo test su un asset
e un periodo soli (che può ingannare per pura fortuna/overfitting)."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import pandas as pd

from .backtester import run_backtest
from .data import fetch_candles
from .manager import ManagerAgent
from .portfolio import Portfolio


def run_batch(products: list[str], granularity: int, hours: int,
              manager_kwargs: dict | None = None, portfolio_kwargs: dict | None = None,
              warmup: int = 25):
    manager_kwargs = manager_kwargs or {}
    portfolio_kwargs = portfolio_kwargs or {}
    end = datetime.now(timezone.utc)
    start = end - timedelta(hours=hours)

    rows = []
    all_trades = []
    for product in products:
        try:
            candles = fetch_candles(product, granularity, start, end)
        except Exception as e:
            rows.append({"product": product, "error": f"{type(e).__name__}: {e}"})
            continue
        if len(candles) <= warmup:
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
        "num_products_tested": len(products),
        "num_products_with_data": int((~results.get("error", pd.Series(dtype=object)).notna()).sum())
        if "error" in results else len(products),
        "total_closed_trades": int(len(closed)),
        "overall_win_rate_pct": float((closed["pnl"] > 0).mean() * 100) if len(closed) else float("nan"),
        "avg_return_pct": float(results["total_return_pct"].mean()) if "total_return_pct" in results else float("nan"),
        "avg_buy_hold_pct": float(results["buy_hold_pct"].mean()) if "buy_hold_pct" in results else float("nan"),
        "avg_max_drawdown_pct": float(results["max_drawdown_pct"].mean()) if "max_drawdown_pct" in results else float("nan"),
    }
    return results, trades_df, summary
