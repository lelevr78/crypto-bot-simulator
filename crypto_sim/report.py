"""Console + CSV reporting."""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Sequence

import pandas as pd

from crypto_sim.backtester import BacktestResult
from crypto_sim.config import RESULTS_DIR
from crypto_sim.walk_forward import WalkForwardResult


def results_to_dataframe(results: Sequence[BacktestResult]) -> pd.DataFrame:
    rows = [r.to_row() for r in results]
    return pd.DataFrame(rows)


def aggregate_stats(results: Sequence[BacktestResult]) -> dict:
    all_trades = [t for r in results for t in r.trade_list]
    n = len(all_trades)
    wins = sum(1 for t in all_trades if t.pnl > 0)
    agg_wr = (wins / n * 100.0) if n else 0.0
    avg_ret = float(pd.Series([r.return_pct for r in results]).mean()) if results else 0.0
    avg_dd = float(pd.Series([r.max_dd_pct for r in results]).mean()) if results else 0.0
    avg_bh = float(pd.Series([r.bh_return_pct for r in results]).mean()) if results else 0.0
    total_trades = sum(r.trades for r in results)
    return {
        "tests": len(results),
        "total_trades": total_trades,
        "aggregated_winrate%": round(agg_wr, 2),
        "avg_return%": round(avg_ret, 2),
        "avg_maxDD%": round(avg_dd, 2),
        "avg_BH%": round(avg_bh, 2),
        "all_trade_pnls_n": n,
    }


def print_summary_table(results: Sequence[BacktestResult]) -> None:
    df = results_to_dataframe(results)
    if df.empty:
        print("(no results)")
        return
    # Pretty fixed-width table
    cols = ["asset", "period", "return%", "trades", "winrate%", "maxDD%", "BH%"]
    df = df[cols]
    print("\n=== BACKTEST SUMMARY ===")
    print(df.to_string(index=False))


def print_aggregate(agg: dict, warn_overfit: bool) -> None:
    print("\n=== AGGREGATE (all tests) ===")
    for k, v in agg.items():
        print(f"  {k}: {v}")
    print(
        "\nNota / Note: in algoritmi reali, un win rate del 45–60% con buon "
        "risk:reward è già solido. Un win rate aggregato >80% in modo "
        "consistente è sospetto (overfitting), non un successo."
    )
    if warn_overfit:
        print(
            "\n*** OVERFITTING WARNING ***\n"
            "Aggregated win rate > 80% across the suite — treat as likely "
            "curve-fit / data artifact, NOT as evidence of a working edge.\n"
            "*** AVVISO OVERFITTING *** Win rate aggregato >80%: sospetto "
            "overfitting, non un risultato affidabile."
        )


def print_walk_forward(wf: WalkForwardResult) -> None:
    print("\n=== WALK-FORWARD (IS tune → OOS freeze) ===")
    print(f"  Best params: {wf.best_params}")
    is_r = wf.is_result
    oos_r = wf.oos_result
    print(
        f"  IS  → return%={is_r.return_pct:.2f}  trades={is_r.trades}  "
        f"winrate%={is_r.win_rate_pct:.2f}  maxDD%={is_r.max_dd_pct:.2f}  BH%={is_r.bh_return_pct:.2f}"
    )
    print(
        f"  OOS → return%={oos_r.return_pct:.2f}  trades={oos_r.trades}  "
        f"winrate%={oos_r.win_rate_pct:.2f}  maxDD%={oos_r.max_dd_pct:.2f}  BH%={oos_r.bh_return_pct:.2f}"
    )


def save_results_csv(
    results: Sequence[BacktestResult],
    agg: dict,
    wf: Optional[WalkForwardResult] = None,
    filename: str = "backtest_summary.csv",
) -> Path:
    root = Path(__file__).resolve().parents[1]
    out_dir = root / RESULTS_DIR
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    df = results_to_dataframe(results)
    # Append aggregate as comment rows via separate file section
    with path.open("w", encoding="utf-8") as f:
        df.to_csv(f, index=False)
        f.write("\n# AGGREGATE\n")
        for k, v in agg.items():
            f.write(f"# {k},{v}\n")
        if wf is not None:
            f.write("\n# WALK_FORWARD\n")
            f.write(f"# best_params,{wf.best_params}\n")
            f.write(
                f"# IS,return%={wf.is_result.return_pct},trades={wf.is_result.trades},"
                f"winrate%={wf.is_result.win_rate_pct},maxDD%={wf.is_result.max_dd_pct},"
                f"BH%={wf.is_result.bh_return_pct}\n"
            )
            f.write(
                f"# OOS,return%={wf.oos_result.return_pct},trades={wf.oos_result.trades},"
                f"winrate%={wf.oos_result.win_rate_pct},maxDD%={wf.oos_result.max_dd_pct},"
                f"BH%={wf.oos_result.bh_return_pct}\n"
            )
    return path
