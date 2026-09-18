# Crypto Bot Simulator

Simulatore di trading crypto su dati pubblici Coinbase, con un **team di agenti**
che vota una decisione (BUY/SELL/HOLD) combinata da un `ManagerAgent`, eseguita
su un **portafoglio virtuale**. Nessun ordine reale viene mai inviato: è uno
strumento di test/ricerca (paper trading).

## Come funziona

- **`crypto_bot/agents.py`** — 4 agenti indipendenti:
  - `Momentum` (incrocio EMA9/EMA21 + rate of change)
  - `MeanReversion` (RSI ipercomprato/ipervenduto, contrarian)
  - `Breakout` (posizione rispetto alle bande di Bollinger)
  - `OrderFlow` — l'agente "anticipatorio": legge l'aggressività dei trade
    (buy vs sell volume) e lo sbilanciamento dell'order book **sulla barra
    ancora in formazione**, per provare a reagire prima che la candela chiuda.
- **`crypto_bot/manager.py`** — combina i voti pesati del team in uno score
  unico, con un filtro di volatilità opzionale.
- **`crypto_bot/portfolio.py`** — portafoglio paper: cash, posizioni, fee,
  stop-loss/take-profit automatici, curva equity, metriche (return, win rate,
  drawdown).
- **`crypto_bot/data.py`** — scarica candele storiche reali dall'API pubblica
  di Coinbase Exchange (nessuna API key) per il backtest.
- **`crypto_bot/feed.py`** — si collega al WebSocket pubblico Coinbase
  Advanced Trade (`market_trades` + `level2`) e aggrega i trade in barre OHLCV
  in tempo reale, tenendo viva la barra "in formazione".
- **`crypto_bot/backtester.py`** / **`crypto_bot/live_paper.py`** — eseguono
  il team di agenti rispettivamente su storico e in live, senza mai inviare
  ordini reali.
- **`app.py`** — dashboard Streamlit con due modalità: *Backtest storico* e
  *Paper trading live*.

## Avvio

```bash
pip install -r requirements.txt
streamlit run app.py
```

## Limiti onesti

- Nessun sistema retail può "vedere" un movimento di prezzo prima che accada
  con certezza: l'agente `OrderFlow` usa segnali di microstruttura (pressione
  di acquisto/vendita, sbilanciamento del book) che *storicamente* a volte
  anticipano la direzione della barra, ma non è una garanzia.
- La latenza a livello di millisecondi/microsecondi è dominio di
  infrastrutture professionali (colocation, HFT); questo strumento compete
  sulla qualità del segnale, non sulla velocità pura.
- Prima di anche solo pensare a soldi reali servirebbe: backtest su molti più
  dati e mercati, walk-forward validation, gestione del rischio più rigorosa
  e — se mai si arrivasse a ordini reali — piena consapevolezza dei rischi
  (il codice attuale esegue **solo simulazioni**).
