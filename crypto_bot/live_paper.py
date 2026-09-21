"""Motore di paper trading live: ad ogni tick valuta il team di agenti sulla
barra ancora in formazione di ogni prodotto ed esegue ordini SOLO simulati
sul Portfolio. Nessun ordine reale viene mai inviato a Coinbase."""
from __future__ import annotations

from datetime import datetime, timezone

from .feed import LiveFeed
from .manager import ManagerAgent
from .portfolio import Portfolio


class LivePaperTrader:
    def __init__(self, feed: LiveFeed, manager: ManagerAgent, portfolio: Portfolio, warmup: int = 20):
        self.feed = feed
        self.manager = manager
        self.portfolio = portfolio
        self.warmup = warmup
        self.last_decisions: dict[str, dict] = {}

    def tick(self):
        now = datetime.now(timezone.utc)
        prices = {}
        for product in self.feed.products:
            df, orderflow, last_price = self.feed.state_for(product)
            if len(df) == 0:
                continue
            price = float(df["close"].iloc[-1])
            prices[product] = price

            stop_trade = self.portfolio.check_stop_and_target(product, price, now)

            if len(df) < self.warmup:
                self.last_decisions[product] = {
                    "action": "HOLD", "score": 0.0, "confidence": 0.0,
                    "reason": f"riscaldamento indicatori: {len(df)}/{self.warmup} barre raccolte",
                }
                continue

            has_position = product in self.portfolio.positions
            decision = self.manager.decide(df, orderflow=orderflow, has_position=has_position)

            executed = None
            blocked_by_min_hold = False
            if stop_trade:
                executed = stop_trade
            elif decision.action == "BUY" and not has_position:
                executed = self.portfolio.buy(product, price, now, reason=decision.reason)
            elif decision.action == "SELL" and has_position:
                if self.portfolio.held_long_enough(product, now):
                    executed = self.portfolio.sell(product, price, now, reason=decision.reason)
                else:
                    blocked_by_min_hold = True

            reason = decision.reason
            if blocked_by_min_hold:
                pos = self.portfolio.positions.get(product)
                elapsed = (now - pos.entry_ts).total_seconds() / 60.0 if pos and pos.entry_ts else 0.0
                remaining = max(0.0, self.portfolio.min_hold_minutes - elapsed)
                reason = f"⏳ vorrebbe vendere ma holding minimo non ancora raggiunto (mancano ~{remaining:.0f} min) | {reason}"

            self.last_decisions[product] = {
                "action": decision.action, "score": decision.score,
                "confidence": decision.confidence, "reason": reason,
                "executed": bool(executed), "blocked_by_min_hold": blocked_by_min_hold,
            }

        if prices:
            self.portfolio.record_equity(now, prices)
        return prices
