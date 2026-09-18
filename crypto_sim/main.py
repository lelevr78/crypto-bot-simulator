"""CLI entry: full multi-asset multi-period suite + walk-forward."""

from __future__ import annotations

import argparse
import sys
from datetime import datetime, timezone
from typing import List

from crypto_sim.agents import (
    BreakoutAgent,
    MeanReversionAgent,
    MomentumAgent,
    OrderFlowAgent,
)
from crypto_sim.backtester import BacktestResult, run_backtest
from crypto_sim.config import (
    BACKTEST_WINDOWS,
    DEFAULT_BUY_THRESHOLD,
    DEFAULT_CASH,
    DEFAULT_FEE_RATE,
    DEFAULT_POSITION_FRACTION,
    DEFAULT_SELL_THRESHOLD,
    DEFAULT_STOP_LOSS_PCT,
    DEFAULT_TAKE_PROFIT_PCT,
    DEFAULT_TIMEFRAME,
    DEFAULT_WEIGHTS,
    PRODUCTS,
    QUICK_PRODUCTS,
    QUICK_WINDOWS,
    WALK_FORWARD_END_OFFSET,
    WALK_FORWARD_LENGTH,
)
from crypto_sim.data.coinbase import load_ohlcv, window_bounds
from crypto_sim.manager import Manager
from crypto_sim.report import (
    aggregate_stats,
    print_aggregate,
    print_summary_table,
    print_walk_forward,
    save_results_csv,
)
from crypto_sim.walk_forward import run_walk_forward


def build_agents():
    return [
        MomentumAgent(),
        MeanReversionAgent(),
        BreakoutAgent(),
        OrderFlowAgent(),
    ]


def run_suite(quick: bool = False) -> int:
    products = QUICK_PRODUCTS if quick else PRODUCTS
    windows = QUICK_WINDOWS if quick else BACKTEST_WINDOWS
    timeframe = DEFAULT_TIMEFRAME
    agents = build_agents()
    manager = Manager(
        weights=DEFAULT_WEIGHTS,
        buy_threshold=DEFAULT_BUY_THRESHOLD,
        sell_threshold=DEFAULT_SELL_THRESHOLD,
    )

    print("Paper-trading only — NO real orders.")
    print(f"Timeframe: {timeframe} | products: {products}")
    print(f"Windows: {windows}")
    print("Fetching Coinbase public OHLCV (cached under data/cache/)...\n")

    results: List[BacktestResult] = []
    api_notes: List[str] = []

    try:
        from tqdm import tqdm
    except ImportError:
        def tqdm(x, **kwargs):
            return x

    tasks = [(p, w) for p in products for w in windows]
    for product_id, (label, end_off, length) in tqdm(tasks, desc="Backtests"):
        start, end = window_bounds(end_off, length)
        try:
            df = load_ohlcv(product_id, timeframe, start, end)
        except Exception as exc:  # noqa: BLE001
            api_notes.append(f"{product_id}/{label}: fetch error {exc}")
            continue
        if df.empty or len(df) < 50:
            api_notes.append(
                f"{product_id}/{label}: insufficient bars ({len(df)}) "
                f"[{start.date()} → {end.date()}]"
            )
            continue
        period = f"{label}_{start.date()}_{end.date()}"
        res = run_backtest(
            df,
            agents,
            manager,
            asset=product_id,
            period=period,
            cash=DEFAULT_CASH,
            fee_rate=DEFAULT_FEE_RATE,
            position_fraction=DEFAULT_POSITION_FRACTION,
            stop_loss_pct=DEFAULT_STOP_LOSS_PCT,
            take_profit_pct=DEFAULT_TAKE_PROFIT_PCT,
        )
        results.append(res)

    print_summary_table(results)
    agg = aggregate_stats(results)
    warn = agg.get("aggregated_winrate%", 0) > 80.0
    print_aggregate(agg, warn_overfit=warn)

    # Walk-forward on BTC-USD combined window
    print("\nRunning walk-forward on BTC-USD...")
    wf_start, wf_end = window_bounds(WALK_FORWARD_END_OFFSET, WALK_FORWARD_LENGTH)
    wf_result = None
    try:
        wf_df = load_ohlcv("BTC-USD", timeframe, wf_start, wf_end)
        if len(wf_df) >= 100:
            wf_result = run_walk_forward(
                wf_df,
                agents,
                asset="BTC-USD",
                cash=DEFAULT_CASH,
                fee_rate=DEFAULT_FEE_RATE,
            )
            print_walk_forward(wf_result)
        else:
            api_notes.append(f"walk-forward: insufficient BTC bars ({len(wf_df)})")
            print("  (skipped — insufficient data)")
    except Exception as exc:  # noqa: BLE001
        api_notes.append(f"walk-forward error: {exc}")
        print(f"  (error: {exc})")

    out = save_results_csv(
        results,
        agg,
        wf_result,
        filename="backtest_summary_quick.csv" if quick else "backtest_summary.csv",
    )
    print(f"\nSaved CSV → {out}")

    if api_notes:
        print("\n=== API / DATA NOTES ===")
        for n in api_notes:
            print(f"  - {n}")

    print(
        f"\nDone at {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M:%S %Z')} "
        "(paper only)."
    )
    return 0


def main(argv: List[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="crypto_sim",
        description="Paper-trading crypto multi-agent simulator (no real orders).",
    )
    sub = parser.add_subparsers(dest="cmd")
    run_p = sub.add_parser("run", help="Run backtest suite + walk-forward")
    run_p.add_argument(
        "--quick",
        action="store_true",
        help="Shorter smoke: 3 assets × 2 shorter windows",
    )
    args = parser.parse_args(argv)
    if args.cmd == "run":
        return run_suite(quick=bool(args.quick))
    parser.print_help()
    return 1


if __name__ == "__main__":
    sys.exit(main())
