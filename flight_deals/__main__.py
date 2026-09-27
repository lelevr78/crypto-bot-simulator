"""Avvio: ``python3 -m flight_deals`` e poi apri http://127.0.0.1:8000"""

from __future__ import annotations

import argparse
import os

from .detector import DealDetector
from .providers import SimulatedProvider, TravelpayoutsProvider
from .scanner import Scanner
from .server import serve
from .store import DealStore


def main() -> None:
    p = argparse.ArgumentParser(description="Radar Voli — monitoraggio offerte voli")
    p.add_argument("--host", default="127.0.0.1")
    p.add_argument("--port", type=int, default=8000)
    p.add_argument("--provider", choices=["simulato", "travelpayouts"],
                   default="travelpayouts" if os.environ.get("TRAVELPAYOUTS_TOKEN") else "simulato")
    p.add_argument("--origins", default="", help="Aeroporti di partenza, es. VRN,VCE,BGY (default: tutti)")
    p.add_argument("--min-discount", type=float, default=0.50, help="Sconto minimo per segnalare (0.5 = 50%%)")
    p.add_argument("--db", default="flight_deals.sqlite", help="File SQLite delle offerte")
    p.add_argument("--ttl-hours", type=float, default=12, help="Ore di validità di un'offerta")
    p.add_argument("--batch", type=int, default=2000, help="Combinazioni analizzate per ciclo")
    p.add_argument("--interval", type=float, default=1.0, help="Secondi tra un ciclo e l'altro")
    args = p.parse_args()

    origins = [c.strip().upper() for c in args.origins.split(",") if c.strip()] or None
    if args.provider == "travelpayouts":
        provider = TravelpayoutsProvider(origins=origins)
        batch, interval = 100, max(args.interval, 2.0)  # rispetta i limiti dell'API
    else:
        provider = SimulatedProvider(origins=origins)
        batch, interval = args.batch, args.interval

    scanner = Scanner(provider, DealDetector(min_discount=args.min_discount), DealStore(args.db, ttl_hours=args.ttl_hours),
                      batch_size=batch, interval=interval)
    if args.provider == "simulato":
        print("Costruzione storico prezzi…")
        scanner.warm_up(min_combinations=400_000)
    scanner.start()

    httpd = serve(scanner, args.host, args.port)
    print(f"Radar Voli attivo ({provider.name}) → http://{args.host}:{args.port}   (Ctrl+C per uscire)")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        scanner.stop()
        httpd.server_close()


if __name__ == "__main__":
    main()
