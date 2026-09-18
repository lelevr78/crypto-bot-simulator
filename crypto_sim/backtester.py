"""Bar-by-bar backtester: signal at t → fill at t+1 open. No look-ahead."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from crypto_sim.agents.base import BaseAgent
from crypto_sim.manager import Decision, Manager
from crypto_sim.portfolio import Portfolio, Trade


@dataclass
class BacktestResult:
    asset: str
    period: str
    return_pct: float
    trades: int
    win_rate_pct: float
    max_dd_pct: float
    bh_return_pct: float
    trade_list: List[Trade] = field(default_factory=list)
    equity_curve: List[float] = field(default_factory=list)
    final_equity: float = 0.0
    params: Dict = field(default_factory=dict)

    def to_row(self) -> dict:
        return {
            "asset": self.asset,
            "period": self.period,
            "return%": round(self.return_pct, 2),
            "trades": self.trades,
            "winrate%": round(self.win_rate_pct, 2),
            "maxDD%": round(self.max_dd_pct, 2),
            "BH%": round(self.bh_return_pct, 2),
        }


def max_drawdown_pct(equity: Sequence[float]) -> float:
    if not equity:
        return 0.0
    arr = np.asarray(equity, dtype=float)
    peak = np.maximum.accumulate(arr)
    dd = (arr - peak) / np.where(peak > 0, peak, 1.0)
    return float(dd.min() * 100.0)


def buy_and_hold_return_pct(df: pd.DataFrame, fee_rate: float) -> float:
    if len(df) < 2:
        return 0.0
    entry = float(df["open"].iloc[1])  # align with first possible fill
    exit_p = float(df["close"].iloc[-1])
    if entry <= 0:
        return 0.0
    # Approximate round-trip fees on B&H
    ret = (exit_p / entry) * (1.0 - fee_rate) / (1.0 + fee_rate) - 1.0
    # Simpler: buy at open[1] with fee, sell at last close with fee
    units = (1.0 - fee_rate) / entry
    final = units * exit_p * (1.0 - fee_rate)
    return (final - 1.0) * 100.0


def run_backtest(
    df: pd.DataFrame,
    agents: Sequence[BaseAgent],
    manager: Manager,
    *,
    asset: str = "",
    period: str = "",
    cash: float = 10_000.0,
    fee_rate: float = 0.003,
    position_fraction: float = 1.0,
    stop_loss_pct: float = 0.03,
    take_profit_pct: float = 0.06,
) -> BacktestResult:
    """Signal on bar i (using data ≤ i) → execute on bar i+1 open.

    Stops checked on bar i+1 using that bar's high/low before/alongside signal fills.
    Order within bar i+1:
      1) If flat and pending BUY → fill at open
      2) If in position: check stops on high/low
      3) If still in position and pending SELL → fill at open (after stops; if stopped already, skip)
    Actually classic approach:
      - At start of bar t+1: apply pending decision from bar t at open
      - During bar t+1: check stops
      - At end of bar t+1: compute new decision for next bar
    """
    if df.empty or len(df) < 30:
        return BacktestResult(
            asset=asset,
            period=period,
            return_pct=0.0,
            trades=0,
            win_rate_pct=0.0,
            max_dd_pct=0.0,
            bh_return_pct=0.0,
        )

    # Precompute causal agent scores (vectorized indicators)
    score_map: Dict[str, pd.Series] = {a.name: a.prepare(df) for a in agents}

    port = Portfolio(
        cash=cash,
        fee_rate=fee_rate,
        position_fraction=position_fraction,
        stop_loss_pct=stop_loss_pct,
        take_profit_pct=take_profit_pct,
    )

    pending: Decision = Decision.HOLD
    n = len(df)
    opens = df["open"].to_numpy(dtype=float)
    highs = df["high"].to_numpy(dtype=float)
    lows = df["low"].to_numpy(dtype=float)
    closes = df["close"].to_numpy(dtype=float)
    times = df.index

    # Warmup: start decisions after enough history; first fill possible at i=1
    for i in range(n):
        # Execute pending from previous bar at this bar's open
        if i > 0 and pending != Decision.HOLD:
            # If BUY and flat: open at open
            # If SELL and long: close at open (stops checked after open fill for new positions)
            if pending == Decision.BUY and not port.in_position:
                port.apply_decision(Decision.BUY, float(opens[i]), times[i])
            elif pending == Decision.SELL and port.in_position:
                port.apply_decision(Decision.SELL, float(opens[i]), times[i])

        # Stops on current bar (after possible open fill)
        if port.in_position:
            port.check_stops(float(highs[i]), float(lows[i]), times[i])

        # Mark equity at close
        port.record_equity(float(closes[i]))

        # New signal using data ≤ i (no look-ahead)
        agent_scores = {name: float(series.iloc[i]) for name, series in score_map.items()}
        result = manager.decide(agent_scores)
        pending = result.decision

    # End of series: close any open position at last close
    port.force_close(float(closes[-1]), times[-1])
    if port.equity_curve:
        port.equity_curve[-1] = port.mark_to_market(float(closes[-1]))

    final_eq = port.equity_curve[-1] if port.equity_curve else cash
    ret_pct = (final_eq / cash - 1.0) * 100.0
    wins = sum(1 for t in port.trades if t.pnl > 0)
    n_trades = len(port.trades)
    win_rate = (wins / n_trades * 100.0) if n_trades else 0.0
    bh = buy_and_hold_return_pct(df, fee_rate)

    return BacktestResult(
        asset=asset,
        period=period,
        return_pct=ret_pct,
        trades=n_trades,
        win_rate_pct=win_rate,
        max_dd_pct=max_drawdown_pct(port.equity_curve),
        bh_return_pct=bh,
        trade_list=list(port.trades),
        equity_curve=list(port.equity_curve),
        final_equity=final_eq,
        params={
            "fee_rate": fee_rate,
            "stop_loss_pct": stop_loss_pct,
            "take_profit_pct": take_profit_pct,
            "weights": dict(manager.weights),
            "buy_threshold": manager.buy_threshold,
            "sell_threshold": manager.sell_threshold,
        },
    )
