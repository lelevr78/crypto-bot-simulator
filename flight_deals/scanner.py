"""Ciclo di scansione continua: preleva tariffe, le analizza, salva le offerte."""

from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from .detector import DealDetector
from .store import DealStore


class Scanner:
    def __init__(self, provider, detector: DealDetector, store: DealStore,
                 batch_size: int = 2000, interval: float = 1.0) -> None:
        self.provider = provider
        self.detector = detector
        self.store = store
        self.batch_size = batch_size
        self.interval = interval
        self.combinations = 0
        self.deals_found = 0
        self.started_at = datetime.now(timezone.utc)
        self.last_scan: datetime | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def warm_up(self, min_combinations: int = 0, max_batches: int = 500) -> None:
        """Costruisce lo storico prezzi finché ogni rotta ha abbastanza campioni
        e sono state analizzate almeno ``min_combinations`` combinazioni."""
        target = len(self.provider.routes())
        for _ in range(max_batches):
            if self.detector.ready_routes() >= target and self.combinations >= min_combinations:
                break
            self.scan_once()

    def scan_once(self) -> int:
        fares = self.provider.sample(self.batch_size)
        found = 0
        for fare in fares:
            deal = self.detector.observe(fare)
            if deal is not None:
                self.store.upsert(deal)
                found += 1
        self.combinations += len(fares)
        self.deals_found += found
        self.last_scan = datetime.now(timezone.utc)
        return found

    def _run(self) -> None:
        last_purge = 0.0
        while not self._stop.is_set():
            self.scan_once()
            if time.monotonic() - last_purge > 60:
                self.store.purge()
                last_purge = time.monotonic()
            self._stop.wait(self.interval)

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="scanner", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=5)

    def status(self) -> dict:
        return {
            "provider": self.provider.name,
            "combinations": self.combinations,
            "deals_found": self.deals_found,
            "routes": len(self.provider.routes()),
            "routes_ready": self.detector.ready_routes(),
            "started_at": self.started_at.isoformat(),
            "last_scan": self.last_scan.isoformat() if self.last_scan else None,
            **self.store.summary(),
        }
