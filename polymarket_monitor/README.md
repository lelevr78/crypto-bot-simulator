# Polymarket arbitrage monitor — solo osservazione

Script Python da eseguire in locale che legge i dati **pubblici e in tempo
reale** di Polymarket (Gamma API per la scoperta dei mercati, CLOB API per
l'order book) e segnala quando lo spread di un mercato crypto Si/No si
allontana dal fair value di 1.00$.

**Cosa NON fa, di proposito:**
- non invia ordini reali, non richiede e non usa nessuna chiave privata
- nessuna esecuzione automatica: e' uno strumento di logging/osservazione
- nessuna promessa di rendimento: i numeri stampati sono stime lorde basate
  sull'order book letto in quel momento, non garanzie su trade futuri

## Come funziona

Un mercato binario Si/No paga 1.00$ per share al lato che vince. Se si
potesse comprare 1 share di Si e 1 share di No spendendo insieme meno di
1.00$ (al prezzo realmente eseguibile, cioe' il *best ask* dell'order book),
l'incasso a scadenza sarebbe garantito qualunque sia l'esito. Lo script
calcola questo scostamento (`1.00 - costo_YES_ask - costo_NO_ask`) su ogni
mercato crypto attivo, ad ogni ciclo di polling.

Come nel simulatore HTML originale, la logica usa due soglie:
- **soglia di ingresso**: sopra questa soglia lo scostamento viene registrato
  come "opportunita' aperta" (solo un appunto, nessun ordine)
- **soglia di uscita**: quando lo scostamento rientra sotto questa soglia,
  l'opportunita' viene "chiusa" nel log, con il guadagno teorico per share
  che si sarebbe potuto catturare tra apertura e chiusura

## Uso

```bash
pip install -r ../requirements.txt   # serve solo "requests", gia' presente
python polymarket_monitor/monitor.py
```

Opzioni principali:

```bash
python polymarket_monitor/monitor.py --entry 0.03 --exit 0.01 --interval 15
python polymarket_monitor/monitor.py --once          # una sola scansione, poi esce
python polymarket_monitor/monitor.py --fee 0.01      # ipotizza una commissione dell'1% per lato
python polymarket_monitor/monitor.py --help          # elenco completo parametri
```

Ogni evento (apertura/chiusura opportunita') viene stampato a console e
aggiunto a `polymarket_monitor/opportunities_log.csv` (percorso
configurabile con `--log-file`).

## Nota

Questo modulo e' indipendente dall'app Streamlit di paper trading crypto
(`crypto_bot/`, avviata con `streamlit run app.py`): non condivide dati ne'
portafoglio, e' un secondo strumento nello stesso repository.
