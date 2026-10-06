# Crypto Bot Simulator

Simulatore di trading crypto su dati pubblici Coinbase, **solo paper trading**:
nessun ordine reale viene mai inviato. Il repository contiene due implementazioni
indipendenti, nate in parallelo, dello stesso concetto (team di agenti che vota
BUY/SELL/HOLD su un portafoglio virtuale):

- **`crypto_bot/` + `app.py`** — dashboard interattiva Streamlit (live + backtest).
- **`crypto_sim/`** — tool a riga di comando con backtest multi-asset e walk-forward.

Non c'è un vincitore designato tra le due: la dashboard è comoda per l'uso
quotidiano (anche da telefono, via Streamlit Cloud) e per il paper trading in
tempo reale; il tool CLI è comodo per lanciare in un colpo solo una suite di
test più estesa e rigorosa. Usa quella più adatta a quello che ti serve.

## 1. Dashboard Streamlit (`crypto_bot/`)

- **`crypto_bot/agents.py`** — 4 agenti indipendenti:
  - `Momentum` (incrocio EMA9/EMA21 + rate of change)
  - `MeanReversion` (RSI ipercomprato/ipervenduto, contrarian)
  - `Breakout` (posizione rispetto alle bande di Bollinger)
  - `OrderFlow` — l'agente "anticipatorio": legge l'aggressività dei trade
    (buy vs sell volume) e lo sbilanciamento dell'order book **sulla barra
    ancora in formazione**, per provare a reagire prima che la candela chiuda.
    Disponibile solo in modalità live (nel backtest storico viene escluso dal
    voto, non essendoci dati di order-flow storici).
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
- **`crypto_bot/backtester.py`** / **`crypto_bot/multi_asset_backtest.py`** /
  **`crypto_bot/batch_backtest.py`** / **`crypto_bot/live_paper.py`** —
  eseguono il team di agenti su un singolo asset, su un portafoglio condiviso
  multi-crypto (l'agente sceglie da solo la crypto migliore), su una batteria
  di asset per validazione statistica, e in live — mai con ordini reali.
- **`app.py`** — dashboard Streamlit con le modalità: *Backtest storico*,
  *Validazione multi-crypto* (con confronto/scelta automatica della soglia),
  *Portafoglio automatico* (multi-crypto, un solo portafoglio condiviso) e
  *Paper trading live*.

### Avvio

```bash
pip install -r requirements.txt
streamlit run app.py
```

## 2. Tool CLI (`crypto_sim/`)

Backtest multi-asset e multi-periodo con walk-forward validation (taratura su
una finestra, verifica su dati mai visti), pensato per lanciare in un colpo
solo una suite di test più estesa di quella della dashboard.

```bash
python3 -m venv .venv
source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -r requirements.txt

python -m crypto_sim run          # suite completa
python -m crypto_sim run --quick  # smoke test più corto
```

Output: tabella `asset | period | return% | trades | winrate% | maxDD% | BH%`,
blocco aggregato, walk-forward IS/OOS, avviso di overfitting se il win rate
aggregato supera l'80% in modo consistente (segnale di sovra-adattamento ai
dati storici, non un successo). CSV salvati in `results/`, cache dati in
`data/cache/`.

## Limiti onesti (validi per entrambe le implementazioni)

- Nessun sistema retail può "vedere" un movimento di prezzo prima che accada
  con certezza: i segnali di order-flow/microstruttura a volte anticipano la
  direzione della barra, ma non è una garanzia.
- La latenza a livello di millisecondi/microsecondi è dominio di
  infrastrutture professionali (colocation, HFT); questi strumenti competono
  sulla qualità del segnale, non sulla velocità pura.
- Un win rate molto alto (es. >80%) ottenuto tarando pesi/soglie sugli stessi
  dati storici testati è quasi sempre un segnale di overfitting, non di un
  vero vantaggio — va sempre riverificato su dati nuovi (out-of-sample/walk-forward).
- Prima di anche solo pensare a soldi reali servirebbe: backtest su molti più
  dati e mercati, validazione walk-forward, gestione del rischio più rigorosa
  e piena consapevolezza dei rischi. Il codice qui presente esegue **solo
  simulazioni**.
