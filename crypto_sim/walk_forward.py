"""Walk-forward: tune on first half (IS), freeze and evaluate on second half (OOS)."""

from __future__ import annotations

from dataclasses import dataclass
from itertools import product
from typing import Dict, List, Sequence, Tuple

import pandas as pd

from crypto_sim.agents.base import BaseAgent
from crypto_sim.backtester import BacktestResult, run_backtest
from crypto_sim.manager import Manager


@dataclass
class WalkForwardResult:
    best_params: Dict
    is_result: BacktestResult
    oos_result: BacktestResult


def _param_grid() -> List[Dict]:
    """Small grid — keep runtime reasonable."""
    weight_sets = [
        {"momentum": 0.40, "mean_reversion": 0.20, "breakout": 0.20, "order_flow": 0.20},
        {"momentum": 0.25, "mean_reversion": 0.35, "breakout": 0.20, "order_flow": 0.20},
        {"momentum": 0.20, "mean_reversion": 0.20, "breakout": 0.40, "order_flow": 0.20},
        {"momentum": 0.30, "mean_reversion": 0.25, "breakout": 0.25, "order_flow": 0.20},
    ]
    buy_ths = [0.15, 0.25, 0.35]
    sell_ths = [-0.15, -0.25, -0.35]
    grid = []
    for w, b, s in product(weight_sets, buy_ths, sell_ths):
        if abs(b) != abs(s):
            # allow asymmetric but prefer mirrored; still include all
            pass
        grid.append({"weights": w, "buy_threshold": b, "sell_threshold": s})
    return grid


def _score_is(result: BacktestResult) -> float:
    """Objective: prefer positive return with controlled DD; mild win-rate term."""
    if result.trades < 3:
        return -1e9
    # Penalize extreme win rates that smell like overfitting on tiny samples
    wr = result.win_rate_pct
    score = result.return_pct - 0.5 * abs(result.max_dd_pct)
    if wr > 80:
        score -= 20.0
    return score


def run_walk_forward(
    df: pd.DataFrame,
    agents: Sequence[BaseAgent],
    *,
    asset: str = "MULTI",
    cash: float = 10_000.0,
    fee_rate: float = 0.003,
) -> WalkForwardResult:
    mid = len(df) // 2
    is_df = df.iloc[:mid].copy()
    oos_df = df.iloc[mid:].copy()

    best = None
    best_score = -1e18
    best_is: BacktestResult | None = None

    for params in _param_grid():
        mgr = Manager(
            weights=params["weights"],
            buy_threshold=params["buy_threshold"],
            sell_threshold=params["sell_threshold"],
        )
        res = run_backtest(
            is_df,
            agents,
            mgr,
            asset=asset,
            period="IS",
            cash=cash,
            fee_rate=fee_rate,
        )
        sc = _score_is(res)
        if sc > best_score:
            best_score = sc
            best = params
            best_is = res

    assert best is not None and best_is is not None
    mgr_oos = Manager(
        weights=best["weights"],
        buy_threshold=best["buy_threshold"],
        sell_threshold=best["sell_threshold"],
    )
    oos = run_backtest(
        oos_df,
        agents,
        mgr_oos,
        asset=asset,
        period="OOS",
        cash=cash,
        fee_rate=fee_rate,
    )
    return WalkForwardResult(best_params=best, is_result=best_is, oos_result=oos)
