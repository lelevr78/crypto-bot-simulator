"""Wrapper minimale per la Gamma API di Polymarket (solo lettura, nessuna
autenticazione richiesta). Serve a scoprire i mercati crypto attivi e a
recuperare i token_id (usati poi dalla CLOB API per leggere l'order book)."""
from __future__ import annotations

import json

import requests

GAMMA_BASE_URL = "https://gamma-api.polymarket.com"

# Parole chiave usate come rete di sicurezza quando i tag del mercato non
# bastano a riconoscerlo come "crypto" (i tag su Polymarket non sono sempre
# compilati in modo affidabile).
CRYPTO_KEYWORDS = (
    "bitcoin", "btc", "ethereum", "eth", "solana", "sol", "crypto",
    "dogecoin", "doge", "xrp", "ripple", "cardano", "ada", "altcoin",
    "stablecoin", "defi", "binance", "coinbase",
)


def _looks_crypto(market: dict) -> bool:
    tags = market.get("tags") or []
    for tag in tags:
        label = (tag.get("label") or "") if isinstance(tag, dict) else str(tag)
        if "crypto" in label.lower():
            return True
    text = f"{market.get('question', '')} {market.get('slug', '')}".lower()
    return any(kw in text for kw in CRYPTO_KEYWORDS)


def _parse_json_field(raw, default):
    """Su Gamma alcuni campi (outcomes, outcomePrices, clobTokenIds) sono
    stringhe JSON annidate dentro il JSON principale: vanno decodificate a parte."""
    if raw is None:
        return default
    if isinstance(raw, (list, dict)):
        return raw
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def fetch_active_crypto_markets(limit: int = 200, timeout: float = 10.0) -> list[dict]:
    """Scarica i mercati binari (Si/No) attivi e non ancora chiusi, filtra
    quelli a tema crypto e restituisce solo i campi utili al monitor:
    id, domanda, token_id del lato SI e del lato NO, volume e liquidita'."""
    params = {
        "closed": "false",
        "active": "true",
        "limit": limit,
        "order": "volume24hr",
        "ascending": "false",
    }
    resp = requests.get(f"{GAMMA_BASE_URL}/markets", params=params, timeout=timeout)
    resp.raise_for_status()
    raw_markets = resp.json()

    markets = []
    for m in raw_markets:
        if not _looks_crypto(m):
            continue

        outcomes = _parse_json_field(m.get("outcomes"), [])
        token_ids = _parse_json_field(m.get("clobTokenIds"), [])
        if len(outcomes) != 2 or len(token_ids) != 2:
            continue  # ci interessano solo i mercati binari Si/No classici

        # L'ordine di outcomes e clobTokenIds e' sempre lo stesso indice per indice.
        idx_yes = next((i for i, o in enumerate(outcomes) if str(o).strip().lower() == "yes"), 0)
        idx_no = 1 - idx_yes

        markets.append({
            "id": m.get("id"),
            "question": m.get("question"),
            "slug": m.get("slug"),
            "yes_token_id": str(token_ids[idx_yes]),
            "no_token_id": str(token_ids[idx_no]),
            "volume24hr": float(m.get("volume24hr") or 0.0),
            "liquidity": float(m.get("liquidity") or 0.0),
        })
    return markets
