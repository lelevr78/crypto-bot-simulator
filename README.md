# Crypto Bot Simulator (Paper Trading)

Simulatore **paper-trading** multi-agente per crypto. **Nessun ordine reale** — solo backtest su OHLCV pubblici Coinbase.

**Paper-trading only / solo simulazione.** No API keys, no live trading.

## Cosa fa

1. Scarica candele pubbliche Coinbase (`BTC-USD`, `ETH-USD`, `SOL-USD`, `XRP-USD`, `ADA-USD`, `LINK-USD`) su timeframe `1h` (anche `1m`/`5m`/`15m` supportati nel loader).
2. Quattro agenti indipendenti producono uno score ∈ [-1, +1] usando **solo dati ≤ barra corrente**:
   - **Momentum** — incrocio EMA veloce/lenta + ROC
   - **Mean-reversion** — RSI contrarian
   - **Breakout** — prezzo vs Bollinger Bands
   - **Order-flow (proxy)** — imbalance body/wick/volume da OHLCV (*non* order book reale)
3. Un **manager** combina gli score con pesi configurabili → `BUY` / `SELL` / `HOLD`.
4. **Portafoglio long-only** virtuale: fee 0.3% per lato (default), stop-loss / take-profit automatici, curva di equity.
5. **Backtester rigoroso**: segnale a `t` → fill a `t+1` open; metriche return%, trades, win rate%, max DD%, buy&hold%.
6. Suite multi-asset × multi-periodo + **walk-forward** (tune IS, freeze OOS).
7. Se il win rate aggregato è **>80%** in modo consistente → stampa **OVERFITTING WARNING** (non successo). In algoritmi reali 45–60% con buon R:R è già solido.

## Installazione

```bash
cd /workspace/crypto-bot-simulator
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

Dipendenze: `requests`, `pandas`, `numpy`, `tqdm` (opzionale).

## Uso

```bash
# Suite completa: ≥6 asset × 2 finestre ~120 giorni su 1h + walk-forward
python -m crypto_sim run

# Smoke test più corto
python -m crypto_sim run --quick
```

Output: tabella `asset | period | return% | trades | winrate% | maxDD% | BH%`, blocco **AGGREGATE**, walk-forward IS/OOS, eventuale avviso overfitting. CSV in `results/`.

Cache dati: `data/cache/*.csv`.

## Struttura

```
crypto-bot-simulator/
  README.md
  requirements.txt
  crypto_sim/
    __init__.py
    __main__.py
    config.py
    indicators.py
    data/coinbase.py
    agents/…
    manager.py
    portfolio.py
    backtester.py
    walk_forward.py
    report.py
    main.py
  results/
```

## Disclaimer

Questo progetto è **educativo**. Fee, slippage e microstructure reali differiscono. L’agente “order-flow” è un **proxy OHLCV**, non true order-flow. Risultati di backtest non garantiscono performance future. **Non usare per trading reale senza review indipendente.**

---

# ✈ Radar Voli — monitoraggio offerte voli

Portale web che analizza di continuo combinazioni di tariffe aeree (origine × destinazione × date × durata) e segnala **solo i ribassi davvero insoliti** (tipicamente dal 50% al 90% in meno del prezzo abituale).

Nessuna dipendenza esterna: basta Python 3.10+.

```bash
python3 -m flight_deals            # poi apri http://127.0.0.1:8000
python3 -m flight_deals --origins VRN,VCE,BGY --min-discount 0.6
```

## Come funziona l'algoritmo

Per ogni rotta si tiene lo storico recente dei prezzi (ultimi 400):

- **prezzo abituale** = mediana dello storico;
- **variazione tipica** = MAD (deviazione assoluta mediana), robusta agli outlier;
- una tariffa è un'**offerta** se lo sconto sulla mediana è ≥ 50% **e** il ribasso è ≥ 2,5 volte la variazione tipica (così le rotte molto volatili non generano falsi allarmi);
- le tariffe anomale **non** entrano nello storico, quindi non abbassano il prezzo di riferimento.

Livelli: *Ottimo prezzo* (≥50%), *Super offerta* (≥60%), *Error fare* (≥75%). Le offerte scadono dopo 12 ore (`--ttl-hours`) o alla data di partenza.

## Fonte dati

| Provider | Uso |
|---|---|
| `simulato` (default) | Tariffe realistiche generate localmente (distanza, stagione, anticipo, rumore) con rari error fare. Ideale per demo e test. |
| `travelpayouts` | Prezzi reali (cache Aviasales) via Travelpayouts Data API. Registrati su travelpayouts.com e imposta `TRAVELPAYOUTS_TOKEN`: il provider si attiva da solo. |

Per aggiungere un'altra fonte (Duffel, Kiwi, …) basta una classe con `name`, `routes()` e `sample(n) -> list[Fare]` in `flight_deals/providers.py`.

## Struttura

```
flight_deals/
├── airports.py   # aeroporti di partenza (VRN, VCE, BGY, MXP, BLQ) e 38 destinazioni
├── providers.py  # sorgenti tariffe (simulata / Travelpayouts)
├── detector.py   # algoritmo di rilevamento anomalie
├── store.py      # archivio SQLite delle offerte
├── scanner.py    # ciclo di scansione continua in background
├── server.py     # API JSON + pagina web
└── static/       # interfaccia (HTML/CSS/JS, responsive, tema chiaro/scuro)
```

API: `GET /api/deals?origin=VRN&min_discount=0.6&max_price=100&month=2026-11&sort=prezzo`, `GET /api/status`, `GET /api/airports`.

Test: `python3 -m unittest tests.test_flight_deals -v`
