"""Logica di rilevamento arbitraggio: SOLO calcolo e log, nessun ordine reale.

Un mercato binario Si/No paga esattamente 1.00$ per share al lato vincente.
Se si puo' comprare 1 share di Si e 1 share di No spendendo insieme meno di
1.00$ (al prezzo realmente eseguibile, cioe' il best ask), l'incasso a
scadenza e' garantito indipendentemente dall'esito: e' arbitraggio reale, non
una previsione. Lo spread monitorato e' questo scostamento da 1.00.

Soglia di ingresso/uscita ricalcano il simulatore HTML originale (mean
reversion dello spread): quando lo spread supera la soglia di ingresso si
registra una "opportunita' aperta" (virtuale, nessun ordine inviato); quando
rientra sotto la soglia di uscita si registra la "chiusura" e il guadagno
teorico per share che si sarebbe potuto catturare."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass
class ArbitrageConfig:
    entry_threshold: float = 0.02   # scostamento minimo da 1.00 per segnalare un'opportunita'
    exit_threshold: float = 0.005   # scostamento sotto il quale l'opportunita' si considera rientrata
    trade_size: float = 100.0       # size teorica per share, solo per stimare il P&L potenziale
    fee_rate: float = 0.0           # costo/commissione stimato per lato, in frazione (0.01 = 1%)


@dataclass
class OpenOpportunity:
    market_id: str
    question: str
    opened_at: datetime
    entry_edge: float               # edge per share al momento dell'apertura (1.00 - costo_buy_both)
    yes_ask: float
    no_ask: float
    available_size: float


class ArbitrageMonitor:
    """Mantiene lo stato delle opportunita' virtuali aperte per applicare la
    logica ingresso/uscita su piu' cicli di polling successivi."""

    def __init__(self, config: ArbitrageConfig):
        self.config = config
        self.open_positions: dict[str, OpenOpportunity] = {}

    def evaluate(self, market: dict, yes_quote: tuple, no_quote: tuple) -> list[dict]:
        """yes_quote/no_quote = (best_bid, best_bid_size, best_ask, best_ask_size)
        cosi' come restituiti da clob_api.best_bid_ask(). Ritorna una lista di
        eventi di log (0, 1 o 2 elementi: al massimo un'apertura e/o una chiusura)."""
        events = []
        now = datetime.now(timezone.utc)
        market_id = market["id"]

        yes_ask, no_ask = yes_quote[2], no_quote[2]
        if yes_ask is None or no_ask is None:
            return events  # book troppo sottile per stimare un prezzo eseguibile

        cost_buy_both = yes_ask + no_ask
        fee_cost = (yes_ask + no_ask) * self.config.fee_rate
        edge = 1.0 - cost_buy_both - fee_cost  # profitto stimato per share, al netto della fee

        available_size = min(
            yes_quote[3] or 0.0,
            no_quote[3] or 0.0,
        )

        already_open = market_id in self.open_positions

        if not already_open and edge >= self.config.entry_threshold:
            opp = OpenOpportunity(
                market_id=market_id, question=market["question"], opened_at=now,
                entry_edge=edge, yes_ask=yes_ask, no_ask=no_ask,
                available_size=available_size,
            )
            self.open_positions[market_id] = opp
            events.append({
                "timestamp": now, "tipo": "APERTURA", "market_id": market_id,
                "question": market["question"], "edge_per_share": edge,
                "yes_ask": yes_ask, "no_ask": no_ask, "size_disponibile": available_size,
                "size_stimata_su_trade_size": min(available_size, self.config.trade_size),
            })
        elif already_open and edge <= self.config.exit_threshold:
            opp = self.open_positions.pop(market_id)
            events.append({
                "timestamp": now, "tipo": "CHIUSURA", "market_id": market_id,
                "question": market["question"], "edge_ingresso": opp.entry_edge,
                "edge_uscita": edge, "durata_secondi": (now - opp.opened_at).total_seconds(),
                "size_disponibile": available_size,
            })

        return events
