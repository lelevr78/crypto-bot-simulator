"""Wrapper minimale per la CLOB API di Polymarket (solo endpoint pubblici in
lettura, nessuna autenticazione, nessuna chiave privata). Legge gli order
book per calcolare il prezzo realmente eseguibile (best bid/ask), non solo
il prezzo medio dichiarato dal mercato."""
from __future__ import annotations

import requests

CLOB_BASE_URL = "https://clob.polymarket.com"
BATCH_SIZE = 50  # limite massimo dell'endpoint /books per singola richiesta


def fetch_books_batch(token_ids: list[str], timeout: float = 10.0) -> dict[str, dict]:
    """Recupera l'order book di piu' token in poche chiamate (invece di una
    per token), spezzando la lista in blocchi da BATCH_SIZE come richiesto
    dall'API. Restituisce un dizionario {token_id: book}."""
    books: dict[str, dict] = {}
    for i in range(0, len(token_ids), BATCH_SIZE):
        chunk = token_ids[i:i + BATCH_SIZE]
        payload = [{"token_id": tid} for tid in chunk]
        resp = requests.post(f"{CLOB_BASE_URL}/books", json=payload, timeout=timeout)
        resp.raise_for_status()
        for book in resp.json():
            asset_id = book.get("asset_id")
            if asset_id:
                books[str(asset_id)] = book
    return books


def best_bid_ask(book: dict | None) -> tuple[float | None, float | None, float | None, float | None]:
    """Estrae dal book il miglior prezzo/size in acquisto e in vendita.
    Ritorna (best_bid_price, best_bid_size, best_ask_price, best_ask_size);
    un valore None significa book vuoto o lato mancante (mercato illiquido)."""
    if not book:
        return None, None, None, None

    bids = book.get("bids") or []
    asks = book.get("asks") or []

    best_bid_price = best_bid_size = None
    if bids:
        best = max(bids, key=lambda b: float(b["price"]))
        best_bid_price, best_bid_size = float(best["price"]), float(best["size"])

    best_ask_price = best_ask_size = None
    if asks:
        best = min(asks, key=lambda a: float(a["price"]))
        best_ask_price, best_ask_size = float(best["price"]), float(best["size"])

    return best_bid_price, best_bid_size, best_ask_price, best_ask_size
