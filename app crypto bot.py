import streamlit as st
import pandas as pd
import numpy as np
import requests
import time
from datetime import datetime, timezone, timedelta
import matplotlib.pyplot as plt

# Configurazione Streamlit
st.set_page_config(page_title="Crypto Bot Simulator", layout="wide")
st.title("🤖 Crypto Trading Bot Simulator")
st.markdown("Simula una strategia di reinvestimento con accantonamento progressivo")

# Costanti
BASE = "https://api.coinbase.com/api/v3/brokerage/market/products/{product_id}/candles"
FEE = 0.005
TP = 0.025
SL = 0.010
MIN_SCORE = 75

# Sidebar per input
st.sidebar.header("⚙️ Parametri")
initial_capital = st.sidebar.number_input("Capitale iniziale (€)", value=10.0, min_value=1.0, step=1.0)
days = st.sidebar.number_input("Giorni di storia (backtest)", value=120, min_value=30, max_value=365, step=10)
crypto = st.sidebar.selectbox("Criptovaluta", ["BTC-USD", "ETH-USD", "SOL-USD", "LINK-USD", "XRP-USD"])

st.sidebar.header("💰 Soglie di accantonamento")
st.sidebar.markdown("Quando profitto >= soglia, accantona % e continua con il resto")
threshold1 = st.sidebar.number_input("Soglia 1 (€ profitto)", value=1.0, min_value=0.1, step=0.1)
accantonamento1 = st.sidebar.number_input("Accantona % della soglia 1", value=80, min_value=0, max_value=100) / 100

threshold2 = st.sidebar.number_input("Soglia 2 (€ profitto)", value=11.0, min_value=1.0, step=1.0)
accantonamento2 = st.sidebar.number_input("Accantona % della soglia 2", value=90, min_value=0, max_value=100) / 100

threshold3 = st.sidebar.number_input("Soglia 3 (€ profitto)", value=20.0, min_value=5.0, step=5.0)
accantonamento3 = st.sidebar.number_input("Accantona % della soglia 3", value=95, min_value=0, max_value=100) / 100

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

def backtest_with_reinvestment(df, initial_capital, threshold1, acc1, threshold2, acc2, threshold3, acc3):
    """Backtest con reinvestimento totale e accantonamento progressivo"""
    d = calculate_indicators(df)
    
    trading_capital = initial_capital
    accantonato = 0.0
    position = None
    trades = []
    capital_history = [{"time": d.index[0], "trading": trading_capital, "accantonato": accantonato}]
    
    for i in range(220, len(d)-1):
        row = d.iloc[i]
        nxt = d.iloc[i+1]
        
        if position is None:
            sc = score(row)
            if sc >= MIN_SCORE:
                entry = float(nxt.open)
                position = {
                    "entry": entry,
                    "capital_before": trading_capital,
                    "target": entry * (1 + TP),
                    "stop": entry * (1 - SL),
                    "score": sc,
                    "time": d.index[i+1],
                    "entry_idx": i+1
                }
        else:
            exit_price = None
            reason = None
            
            if nxt.low <= position["stop"]:
                exit_price = position["stop"]
                reason = "STOP"
            elif nxt.high >= position["target"]:
                exit_price = position["target"]
                reason = "TARGET"
            elif nxt.close < nxt.ema50:
                exit_price = float(nxt.close)
                reason = "TREND_EXIT"
            
            if exit_price is not None:
                gross = exit_price / position["entry"] - 1
                net_factor = (1 + gross) * (1 - FEE) * (1 - FEE)
                new_capital = position["capital_before"] * net_factor
                
                trades.append({
                    "entry_time": position["time"],
                    "exit_time": d.index[i+1],
                    "entry": position["entry"],
                    "exit": exit_price,
                    "score": position["score"],
                    "reason": reason,
                    "gross_pct": gross*100,
                    "net_pct": (new_capital/position["capital_before"]-1)*100,
                    "capital_after": new_capital
                })
                
                trading_capital = new_capital
                
                # Calcola profitto totale
                total_capital = trading_capital + accantonato
                profitto = total_capital - initial_capital
                
                # Verifica soglie di accantonamento
                if profitto >= threshold3:
                    accantonare = (trading_capital - position["capital_before"]) * acc3
                    if accantonare > 0:
                        accantonato += accantonare
                        trading_capital -= accantonare
                elif profitto >= threshold2:
                    accantonare = (trading_capital - position["capital_before"]) * acc2
                    if accantonare > 0:
                        accantonato += accantonare
                        trading_capital -= accantonare
                elif profitto >= threshold1:
                    accantonare = (trading_capital - position["capital_before"]) * acc1
                    if accantonare > 0:
                        accantonato += accantonare
                        trading_capital -= accantonare
                
                position = None
                capital_history.append({
                    "time": d.index[i+1],
                    "trading": trading_capital,
                    "accantonato": accantonato
                })
    
    return trading_capital, accantonato, trades, capital_history

# Main
st.markdown(f"**Capitale iniziale:** €{initial_capital} | **Periodo:** {days} giorni | **Asset:** {crypto}")

if st.button("▶️ Esegui Simulazione", key="simulate"):
    st.info("⏳ Scaricamento dati da Coinbase...")
    
    df = fetch_candles(crypto, days)
    
    if df is not None and len(df) > 250:
        st.success(f"✓ Scaricate {len(df)} candele")
        
        # Esegui backtest
        with st.spinner("Analisi in corso..."):
            trading_final, accantonato_final, trades_list, capital_hist = backtest_with_reinvestment(
                df, initial_capital,
                threshold1, accantonamento1,
                threshold2, accantonamento2,
                threshold3, accantonamento3
            )
        
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
        if capital_hist:
            hist_df = pd.DataFrame(capital_hist)
            hist_df["totale"] = hist_df["trading"] + hist_df["accantonato"]
            
            fig, ax = plt.subplots(figsize=(12, 5))
            ax.plot(hist_df["time"], hist_df["trading"], label="Capitale Attivo", linewidth=2, color="blue")
            ax.plot(hist_df["time"], hist_df["accantonato"], label="Accantonato", linewidth=2, color="green")
            ax.plot(hist_df["time"], hist_df["totale"], label="Totale", linewidth=2.5, color="red", linestyle="--")
            ax.axhline(y=initial_capital, color="gray", linestyle=":", label="Capitale Iniziale")
            ax.set_xlabel("Data")
            ax.set_ylabel("€")
            ax.set_title(f"Andamento Capitale - {crypto}")
            ax.legend()
            ax.grid(True, alpha=0.3)
            st.pyplot(fig)
        
        # Statistiche trade
        if trades_list:
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
            
            # Tabella trade
            st.subheader("📊 Dettaglio Trade")
            display_trades = trades_df[["entry_time", "exit_time", "entry", "exit", "net_pct", "reason"]].copy()
            display_trades["entry_time"] = display_trades["entry_time"].astype(str)
            display_trades["exit_time"] = display_trades["exit_time"].astype(str)
            st.dataframe(display_trades, use_container_width=True)
            
            # CSV download
            csv = trades_df.to_csv(index=False)
            st.download_button(
                label="📥 Scarica Trade CSV",
                data=csv,
                file_name=f"trades_{crypto}_{days}d.csv",
                mime="text/csv"
            )
        else:
            st.warning("⚠️ Nessun trade eseguito nel periodo")
    else:
        st.error(f"❌ Errore: Dati insufficienti da Coinbase")

st.markdown("---")
st.markdown("**Note:** Simulazione senza leva. TP: +2.5% | SL: -1.0% | Fee: 0.5% per lato")
