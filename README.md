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
