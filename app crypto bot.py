import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timezone, timedelta
import matplotlib.pyplot as plt

# Configurazione Streamlit
st.set_page_config(page_title="Crypto Bot Simulator", layout="wide")
st.title("🤖 Crypto Trading Bot Simulator - Multi Asset Autonomo")
st.markdown("Bot autonomo che sceglie quale crypto comprare/vendere in base all'andamento")

# Costanti
BASE = "https://api.coinbase.com/api/v3/brokerage/market/products/{product_id}/candles"

# TOP 20 CRYPTO COINBASE (lista fissa)
TOP_CRYPTOS = [
    "BTC-USD", "ETH-USD", "SOL-USD", "LINK-USD", "XRP-USD",
    "ADA-USD", "AVAX-USD", "DOGE-USD", "MATIC-USD", "LTC-USD",
    "UNI-USD", "ATOM-USD", "POLKADOT-USD", "SHIB-USD", "TRX-USD",
    "ARB-USD", "OP-USD", "NEAR-USD", "FIL-USD", "HBAR-USD"
]

FEE = 0.005
TP = 0.03  # +3% quando vende in profitto
SL = 0.015  # -1.5% per stop loss
MIN_SCORE = 70  # Score minimo per entrare
EXIT_SCORE = 50  # Score per uscire da posizione

# Sidebar per input
st.sidebar.header("⚙️ Parametri")
initial_capital = st.sidebar.number_input("Capitale iniziale (€)", value=10.0, min_value=1.0, step=1.0)
days = st.sidebar.number_input("Giorni di storia (backtest)", value=120, min_value=30, max_value=365, step=10)

st.sidebar.header("💰 Soglie di accantonamento")
st.sidebar.markdown("Quando profitto >= soglia, accantona % e continua con il resto")
threshold1 = st.sidebar.number_input("Soglia 1 (€ profitto)", value=1.0, min_value=0.1, step=0.1)
accantonamento1 = st.sidebar.number_input("Accantona % soglia 1", value=80, min_value=0, max_value=100) / 100

threshold2 = st.sidebar.number_input("Soglia 2 (€ profitto)", value=5.0, min_value=1.0, step=1.0)
accantonamento2 = st.sidebar.number_input("Accantona % soglia 2", value=90, min_value=0, max_value=100) / 100

threshold3 = st.sidebar.number_input("Soglia 3 (€ profitto)", value=10.0, min_value=5.0, step=5.0)
accantonamento3 = st.sidebar.number_input("Accantona % soglia 3", value=95, min_value=0, max_value=100) / 100

st.sidebar.markdown("---")
st.sidebar.info(f"🤖 Il bot monitora {len(TOP_CRYPTOS)} crypto e sceglie autonomamente quale comprare/vendere")

def fetch_candles(product, days):
    """Scarica candele 1h da Coinbase per gli ultimi N giorni"""
    end = int(time.time())
    start = int((datetime.now(timezone.utc) - timedelta(days=days)).timestamp())
    
    all_candles = []
    step = 350 * 3600
    cur = start
    request_count = 0
    
    progress_bar = st.progress(0)
    status_text = st.empty()
    
    while cur < end:
        nxt = min(cur + step, end)
        request_count += 1
        
        params = {
            "start": str(cur), "end": str(nxt),
            "granularity": "ONE_HOUR", "limit": 350
        }
        
        try:
            status_text.text(f"Download... Richiesta {request_count}")
            r = requests.get(BASE.format(product_id=product), params=params, timeout=20)
            
            if r.status_code != 200:
                st.error(f"Errore Coinbase: HTTP {r.status_code}")
                return None
            
            data = r.json().get("candles", [])
            if data:
                all_candles.extend(data)
            
            cur = nxt
            progress_bar.progress(min((cur - start) / (end - start), 1.0))
            time.sleep(0.15)
            
        except Exception as e:
            st.error(f"Errore di connessione: {e}")
            return None
    
    progress_bar.empty()
    status_text.empty()
    
    if not all_candles:
        return None
    
    # Costruisci DataFrame
    df = pd.DataFrame(all_candles)
    
    # Converti campi
    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    
    df["start"] = pd.to_numeric(df["start"], errors="coerce").astype(int)
    df["time"] = pd.to_datetime(df["start"], unit="s", utc=True)
    
    # Ordina e deduplicato
    df = df.sort_values("time")
    df = df.drop_duplicates("start")
    df = df.set_index("time")[["open", "high", "low", "close", "volume"]]
    
    return df

def calculate_indicators(df):
    """Calcola EMA, RSI, MACD"""
    d = df.copy()
    d["ema20"] = d.close.ewm(span=20, adjust=False).mean()
    d["ema50"] = d.close.ewm(span=50, adjust=False).mean()
    d["ema200"] = d.close.ewm(span=200, adjust=False).mean()

    delta = d.close.diff()
    gain = delta.clip(lower=0).ewm(alpha=1/14, adjust=False).mean()
    loss = (-delta.clip(upper=0)).ewm(alpha=1/14, adjust=False).mean()
    rs = gain / loss.replace(0, np.nan)
    d["rsi"] = 100 - (100 / (1 + rs))

    ema12 = d.close.ewm(span=12, adjust=False).mean()
    ema26 = d.close.ewm(span=26, adjust=False).mean()
    d["macd"] = ema12 - ema26
    d["macd_signal"] = d.macd.ewm(span=9, adjust=False).mean()

    d["vol_ma20"] = d.volume.rolling(20).mean()
    tr = pd.concat([
        d.high-d.low,
        (d.high-d.close.shift()).abs(),
        (d.low-d.close.shift()).abs()
    ], axis=1).max(axis=1)
    d["atr"] = tr.rolling(14).mean()
    return d

def score(row):
    """Calcola score di ingresso"""
    s = 0
    if row.close > row.ema20: s += 15
    if row.ema20 > row.ema50: s += 15
    if row.ema50 > row.ema200: s += 15
    if 50 <= row.rsi <= 68: s += 15
    if row.macd > row.macd_signal: s += 15
    if row.volume > row.vol_ma20: s += 10
    if row.atr / row.close < 0.04: s += 5
    return s

def backtest_multi_crypto(data_dict, initial_capital, threshold1, acc1, threshold2, acc2, threshold3, acc3):
    """
    Backtest autonomo multi-crypto.
    Il bot sceglie quale crypto comprare/vendere in base al score migliore.
    """
    # Calcola indicatori per tutte le crypto
    indicators_dict = {}
    for crypto, df in data_dict.items():
        if df is not None and len(df) > 220:
            indicators_dict[crypto] = calculate_indicators(df)
    
    if not indicators_dict:
        return None, None, None, None
    
    # Trova il numero di candele (stesso per tutte)
    num_candles = len(list(indicators_dict.values())[0])
    
    trading_capital = initial_capital
    accantonato = 0.0
    position = None  # {"crypto": "BTC-USD", "entry_price": X, "entry_time": T, "entry_capital": X}
    trades = []
    capital_history = []
    
    start_idx = 220
    
    for i in range(start_idx, num_candles - 1):
        # Se non hai posizione, cerca la crypto migliore
        if position is None:
            best_crypto = None
            best_score = MIN_SCORE - 1
            
            for crypto, ind_df in indicators_dict.items():
                if i < len(ind_df):
                    row = ind_df.iloc[i]
                    sc = score(row)
                    
                    if sc > best_score:
                        best_score = sc
                        best_crypto = crypto
            
            # Se trovata una crypto buona, entra
            if best_crypto is not None and best_score >= MIN_SCORE:
                ind_df = indicators_dict[best_crypto]
                nxt = ind_df.iloc[i + 1]
                entry_price = float(nxt.open)
                
                position = {
                    "crypto": best_crypto,
                    "entry_price": entry_price,
                    "entry_time": ind_df.index[i + 1],
                    "entry_capital": trading_capital,
                    "entry_score": best_score,
                    "entry_idx": i + 1
                }
        
        # Se hai posizione, monitora quella crypto
        else:
            crypto = position["crypto"]
            ind_df = indicators_dict[crypto]
            
            if i + 1 < len(ind_df):
                nxt = ind_df.iloc[i + 1]
                row = ind_df.iloc[i]
                current_score = score(row)
                
                exit_price = None
                reason = None
                
                # Criteri di uscita
                # 1. Hit TP o SL
                if nxt.low <= position["entry_price"] * (1 - SL):
                    exit_price = position["entry_price"] * (1 - SL)
                    reason = "STOP_LOSS"
                elif nxt.high >= position["entry_price"] * (1 + TP):
                    exit_price = position["entry_price"] * (1 + TP)
                    reason = "TAKE_PROFIT"
                # 2. Score scende troppo (trend gira)
                elif current_score < EXIT_SCORE:
                    exit_price = float(nxt.close)
                    reason = "TREND_EXIT"
                # 3. Chiude sotto EMA50 (trend negativo)
                elif nxt.close < nxt.ema50:
                    exit_price = float(nxt.close)
                    reason = "EMA50_EXIT"
                
                if exit_price is not None:
                    # Calcola profitto
                    gross = exit_price / position["entry_price"] - 1
                    net_factor = (1 + gross) * (1 - FEE) * (1 - FEE)
                    new_capital = position["entry_capital"] * net_factor
                    
                    trades.append({
                        "entry_time": position["entry_time"],
                        "exit_time": ind_df.index[i + 1],
                        "crypto": crypto,
                        "entry": position["entry_price"],
                        "exit": exit_price,
                        "score": position["entry_score"],
                        "reason": reason,
                        "gross_pct": gross*100,
                        "net_pct": (new_capital/position["entry_capital"]-1)*100,
                        "capital_after": new_capital
                    })
                    
                    trading_capital = new_capital
                    
                    # Verifica accantonamento
                    total_capital = trading_capital + accantonato
                    profitto = total_capital - initial_capital
                    
                    if profitto >= threshold3:
                        da_accantonare = (trading_capital - position["entry_capital"]) * acc3
                        if da_accantonare > 0:
                            accantonato += da_accantonare
                            trading_capital -= da_accantonare
                    elif profitto >= threshold2:
                        da_accantonare = (trading_capital - position["entry_capital"]) * acc2
                        if da_accantonare > 0:
                            accantonato += da_accantonare
                            trading_capital -= da_accantonare
                    elif profitto >= threshold1:
                        da_accantonare = (trading_capital - position["entry_capital"]) * acc1
                        if da_accantonare > 0:
                            accantonato += da_accantonare
                            trading_capital -= da_accantonare
                    
                    position = None
        
        # Registra capitale ogni 24 candele (ogni giorno)
        if i % 24 == 0:
            first_crypto = list(indicators_dict.keys())[0]
            first_df = indicators_dict[first_crypto]
            if i < len(first_df):
                capital_history.append({
                    "time": first_df.index[i],
                    "trading": trading_capital,
                    "accantonato": accantonato
                })
    
    return trading_capital, accantonato, trades, capital_history

# Main
st.markdown(f"**Capitale iniziale:** €{initial_capital} | **Periodo:** {days} giorni | **Asset:** TOP {len(TOP_CRYPTOS)} Crypto")

if st.button("▶️ Esegui Simulazione Autonoma", key="simulate"):
    st.info(f"⏳ Scaricamento dati da Coinbase per {len(TOP_CRYPTOS)} crypto...")
    
    # Scarica tutte le crypto
    data_dict = {}
    progress = st.progress(0)
    
    for idx, crypto in enumerate(TOP_CRYPTOS):
        progress.progress((idx + 1) / len(TOP_CRYPTOS))
        df = fetch_candles(crypto, days)
        data_dict[crypto] = df
    
    progress.empty()
    
    # Verifica che almeno 15 crypto abbiano dati sufficienti
    valid_cryptos = [c for c, df in data_dict.items() if df is not None and len(df) > 250]
    
    if len(valid_cryptos) >= 15:
        st.success(f"✓ Scaricate {len(valid_cryptos)} crypto valide")
        
        # Esegui backtest multi-crypto
        with st.spinner("Bot autonomo in analisi..."):
            trading_final, accantonato_final, trades_list, capital_hist = backtest_multi_crypto(
                data_dict, initial_capital,
                threshold1, accantonamento1,
                threshold2, accantonamento2,
                threshold3, accantonamento3
            )
        
        if trading_final is not None:
            total_final = trading_final + accantonato_final
            profitto_totale = total_final - initial_capital
            profitto_pct = (profitto_totale / initial_capital) * 100
            
            # KPI
            col1, col2, col3, col4, col5 = st.columns(5)
            col1.metric("💼 Capitale Attivo", f"€{trading_final:.2f}")
            col2.metric("🏦 Accantonato", f"€{accantonato_final:.2f}")
            col3.metric("📊 Totale", f"€{total_final:.2f}")
            col4.metric("💹 Profitto", f"€{profitto_totale:.2f}")
            col5.metric("📈 +%", f"{profitto_pct:.2f}%")
            
            # Grafico capitale nel tempo
            if capital_hist and len(capital_hist) > 1:
                hist_df = pd.DataFrame(capital_hist)
                hist_df["totale"] = hist_df["trading"] + hist_df["accantonato"]
                
                fig, ax = plt.subplots(figsize=(12, 5))
                ax.plot(hist_df["time"], hist_df["trading"], label="Capitale Attivo", linewidth=2, color="blue")
                ax.plot(hist_df["time"], hist_df["accantonato"], label="Accantonato", linewidth=2, color="green")
                ax.plot(hist_df["time"], hist_df["totale"], label="Totale", linewidth=2.5, color="red", linestyle="--")
                ax.axhline(y=initial_capital, color="gray", linestyle=":", label="Capitale Iniziale")
                ax.set_xlabel("Data")
                ax.set_ylabel("€")
                ax.set_title("Andamento Capitale - Bot Autonomo Multi-Crypto")
                ax.legend()
                ax.grid(True, alpha=0.3)
                st.pyplot(fig)
            
            # Statistiche trade
            if trades_list and len(trades_list) > 0:
                trades_df = pd.DataFrame(trades_list)
                num_trades = len(trades_df)
                wins = len(trades_df[trades_df["net_pct"] > 0])
                win_rate = (wins / num_trades * 100) if num_trades > 0 else 0
                avg_profit = trades_df["net_pct"].mean()
                
                col1, col2, col3, col4 = st.columns(4)
                col1.metric("📋 N. Trade", num_trades)
                col2.metric("✅ Win Rate", f"{win_rate:.1f}%")
                col3.metric("📈 Avg Profit/Trade", f"{avg_profit:.2f}%")
                col4.metric("🏆 Trades Vincenti", wins)
                
                # Statistiche per crypto
                st.subheader("📊 Performance per Crypto")
                crypto_perf = trades_df.groupby("crypto").agg({
                    "net_pct": ["count", "mean", "sum"],
                    "capital_after": "last"
                }).round(2)
                crypto_perf.columns = ["N. Trade", "Avg %", "Tot %", "Capital"]
                st.dataframe(crypto_perf, use_container_width=True)
                
                # Tabella dettaglio trade
                st.subheader("📋 Storico Operazioni Dettagliato")
                display_trades = trades_df[["entry_time", "exit_time", "crypto", "entry", "exit", "net_pct", "reason"]].copy()
                display_trades["entry_time"] = display_trades["entry_time"].astype(str).str[:16]
                display_trades["exit_time"] = display_trades["exit_time"].astype(str).str[:16]
                display_trades.rename(columns={
                    "entry_time": "Ingresso",
                    "exit_time": "Uscita",
                    "crypto": "Asset",
                    "entry": "Prezzo In",
                    "exit": "Prezzo Out",
                    "net_pct": "Profitto %",
                    "reason": "Motivo"
                }, inplace=True)
                st.dataframe(display_trades, use_container_width=True)
                
                # CSV download
                csv = trades_df.to_csv(index=False)
                st.download_button(
                    label="📥 Scarica Trade CSV",
                    data=csv,
                    file_name=f"trades_multibot_{days}d.csv",
                    mime="text/csv"
                )
            else:
                st.warning("⚠️ Nessun trade eseguito nel periodo")
        else:
            st.error("❌ Errore nel backtest")
    else:
        st.error(f"❌ Dati insufficienti: {len(valid_cryptos)}/{len(TOP_CRYPTOS)} crypto valide. Riprovare.")

st.markdown("---")
st.markdown("**ℹ️ Info:** Bot 100% autonomo | TP: +3% | SL: -1.5% | Min Score: 70 | Exit Score: 50 | Fee: 0.5% per lato")
