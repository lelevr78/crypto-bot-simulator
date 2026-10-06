#!/usr/bin/env python3
"""Monitor di SOLA OSSERVAZIONE per opportunita' di arbitraggio sui prediction
market crypto di Polymarket.

Cosa fa:
  - scarica periodicamente i mercati crypto attivi dalla Gamma API
  - legge l'order book reale (best bid/ask) di ciascun mercato dalla CLOB API
  - calcola lo scostamento di YES+NO dal fair value di 1.00$
  - quando lo scostamento supera la soglia di ingresso, registra una
    "opportunita'" virtuale; quando rientra sotto la soglia di uscita, la
    chiude e stampa il guadagno teorico per share
  - scrive tutto anche su un file CSV di log

Cosa NON fa (di proposito):
  - non invia ordini, non richiede e non usa chiavi private
  - non promette rendimenti: e' uno strumento di osservazione/logging, i
    numeri che stampa sono stime lorde basate sull'order book al momento
    della lettura, non garanzie di esecuzione futura

Uso:
    python polymarket_monitor/monitor.py
    python polymarket_monitor/monitor.py --entry 0.03 --exit 0.01 --interval 15
    python polymarket_monitor/monitor.py --once      # una sola scansione, poi esce
"""
from __future__ import annotations

import argparse
import csv
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Permette sia `python polymarket_monitor/monitor.py` sia `python -m polymarket_monitor.monitor`.
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from polymarket_monitor.arbitrage import ArbitrageConfig, ArbitrageMonitor
    from polymarket_monitor.clob_api import best_bid_ask, fetch_books_batch
    from polymarket_monitor.gamma_api import fetch_active_crypto_markets
else:
    from .arbitrage import ArbitrageConfig, ArbitrageMonitor
    from .clob_api import best_bid_ask, fetch_books_batch
    from .gamma_api import fetch_active_crypto_markets

DEFAULT_LOG_PATH = Path(__file__).resolve().parent / "opportunities_log.csv"
CSV_FIELDS = [
    "timestamp", "tipo", "market_id", "question", "edge_per_share",
    "edge_ingresso", "edge_uscita", "yes_ask", "no_ask",
    "size_disponibile", "size_stimata_su_trade_size", "durata_secondi",
]


def _append_to_csv(log_path: Path, event: dict) -> None:
    is_new = not log_path.exists()
    with log_path.open("a", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=CSV_FIELDS, extrasaction="ignore")
        if is_new:
            writer.writeheader()
        row = dict(event)
        row["timestamp"] = event["timestamp"].isoformat()
        writer.writerow(row)


def _print_event(event: dict) -> None:
    ts = event["timestamp"].strftime("%H:%M:%S")
    if event["tipo"] == "APERTURA":
        print(
            f"[{ts}] APERTURA  {event['question'][:70]:<70} "
            f"edge={event['edge_per_share']*100:+.2f}c  "
            f"YES_ask={event['yes_ask']:.3f} NO_ask={event['no_ask']:.3f}  "
            f"size_disp={event['size_disponibile']:.0f}"
        )
    else:
        print(
            f"[{ts}] CHIUSURA  {event['question'][:70]:<70} "
            f"ingresso={event['edge_ingresso']*100:+.2f}c -> uscita={event['edge_uscita']*100:+.2f}c  "
            f"durata={event['durata_secondi']:.0f}s"
        )


def run_scan(gamma_limit: int, monitor: ArbitrageMonitor, log_path: Path) -> int:
    """Esegue un ciclo completo: scarica mercati, legge i book, valuta le
    soglie, stampa e logga gli eventi. Ritorna il numero di mercati osservati."""
    markets = fetch_active_crypto_markets(limit=gamma_limit)
    if not markets:
        print("Nessun mercato crypto attivo trovato in questo momento.")
        return 0

    token_ids = []
    for m in markets:
        token_ids.append(m["yes_token_id"])
        token_ids.append(m["no_token_id"])
    books = fetch_books_batch(token_ids)

    for market in markets:
        yes_quote = best_bid_ask(books.get(market["yes_token_id"]))
        no_quote = best_bid_ask(books.get(market["no_token_id"]))
        events = monitor.evaluate(market, yes_quote, no_quote)
        for event in events:
            _print_event(event)
            _append_to_csv(log_path, event)

    return len(markets)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--entry", type=float, default=0.02,
                         help="soglia di ingresso: scostamento minimo da 1.00$ per share (default 0.02 = 2 centesimi)")
    parser.add_argument("--exit", dest="exit_th", type=float, default=0.005,
                         help="soglia di uscita: scostamento sotto il quale l'opportunita' si chiude (default 0.005)")
    parser.add_argument("--size", type=float, default=100.0,
                         help="size teorica per share usata solo per stimare il potenziale, in $ (default 100)")
    parser.add_argument("--fee", type=float, default=0.0,
                         help="commissione stimata per lato, come frazione (default 0.0 = nessuna fee)")
    parser.add_argument("--interval", type=float, default=10.0,
                         help="secondi di attesa tra una scansione e la successiva (default 10)")
    parser.add_argument("--limit", type=int, default=200,
                         help="numero massimo di mercati da scaricare per scansione (default 200)")
    parser.add_argument("--log-file", type=Path, default=DEFAULT_LOG_PATH,
                         help=f"percorso del file CSV di log (default {DEFAULT_LOG_PATH})")
    parser.add_argument("--once", action="store_true",
                         help="esegue una sola scansione ed esce, invece di girare in loop")
    args = parser.parse_args()

    if args.exit_th >= args.entry:
        parser.error("--exit deve essere minore di --entry (altrimenti l'opportunita' si chiude subito)")

    config = ArbitrageConfig(
        entry_threshold=args.entry, exit_threshold=args.exit_th,
        trade_size=args.size, fee_rate=args.fee,
    )
    monitor = ArbitrageMonitor(config)

    print("=" * 78)
    print("Polymarket arbitrage monitor — SOLA OSSERVAZIONE, nessun ordine reale")
    print(f"Soglia ingresso: {args.entry*100:.1f}c   Soglia uscita: {args.exit_th*100:.1f}c   "
          f"Fee: {args.fee*100:.2f}%   Intervallo: {args.interval:.0f}s")
    print(f"Log CSV: {args.log_file}")
    print("=" * 78)

    try:
        while True:
            started = time.monotonic()
            try:
                n = run_scan(args.limit, monitor, args.log_file)
                now_str = datetime.now(timezone.utc).strftime("%H:%M:%S UTC")
                print(f"[{now_str}] scansione completata — {n} mercati osservati, "
                      f"{len(monitor.open_positions)} opportunita' aperte")
            except Exception as e:
                print(f"Errore durante la scansione ({type(e).__name__}: {e}) — riprovo al prossimo ciclo.")

            if args.once:
                break
            elapsed = time.monotonic() - started
            time.sleep(max(0.0, args.interval - elapsed))
    except KeyboardInterrupt:
        print("\nInterrotto dall'utente. Nessun ordine e' mai stato inviato: era solo osservazione.")


if __name__ == "__main__":
    main()
